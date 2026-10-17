"""One voice conversation over a WebSocket: hear an utterance, run the chat agent on it, speak
the answer. Turns are recorded in the chat like typed ones (see docs/VOICE.md for the protocol).

While a turn runs, incoming audio is not listened to: without echo cancellation the answer
coming out of the speakers would sound like the user talking. The app interrupts explicitly."""

import asyncio
import json
import logging
import re
from collections.abc import Callable, Iterator

import numpy as np
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from ...core import errors
from ...core.settings import settings
from ...providers import registry
from ...voice import stt, tts
from ...voice.endpointer import RATE, Endpointer
from ...voice.speech_text import sentences
from .chats import Chats

log = logging.getLogger(__name__)

LOOKING = "One moment."  # said when the agent starts a search, so the silence isn't unexplained
YES = re.compile(r"^\W*(yes|yeah|yep|sure|ok(ay)?|go ahead|do it|approve[d]?)\b", re.IGNORECASE)
NO = re.compile(r"^\W*(no|nope|cancel|don'?t|stop)\b", re.IGNORECASE)


class VoiceCall:
    def __init__(self, ws: WebSocket, chats: Chats, chat_id: str, on_new_files: Callable[[], None]) -> None:
        self.ws, self.chats, self.chat_id, self.on_new_files = ws, chats, chat_id, on_new_files
        self.endpointer = Endpointer()
        # an utterance, an approval, a reminder to say (str), or the end (None)
        self.work: asyncio.Queue[np.ndarray | bool | str | None] = asyncio.Queue()
        self.busy = False
        self.interrupted = asyncio.Event()
        self.speaker: tts.Speaker | None = None
        self.loop = asyncio.get_running_loop()  # made in the WebSocket handler; announce() needs it

    # ---------- the connection ----------

    def announce(self, text: str) -> None:
        """Say something unasked (a reminder going off), from any thread: it waits for the
        current turn to finish, so it never cuts into an answer."""
        self.loop.call_soon_threadsafe(self.work.put_nowait, text)

    async def run(self) -> None:
        if not await self._prepare():
            return
        receiver = asyncio.create_task(self._receive())
        try:
            while (item := await self.work.get()) is not None:
                self.busy = True
                self.interrupted.clear()
                try:
                    await self._turn(item)
                finally:
                    self.busy = False
                    await self._send({"type": "turn_done"})
        except WebSocketDisconnect:
            pass
        finally:
            receiver.cancel()

    async def _prepare(self) -> bool:
        """Load the speech models and warm the chat model, then say ready (or why not)."""
        try:
            self.speaker = await asyncio.to_thread(tts.load)
            await asyncio.to_thread(stt.load)
        except errors.LumenError as e:
            await self._send({"type": "error", "code": e.code, "message": e.message, "hint": e.hint})
            await self.ws.close(code=1011)
            return False
        asyncio.get_running_loop().run_in_executor(None, _warm_chat_model)
        await self._send(
            {
                "type": "ready",
                "chat_id": self.chat_id,
                "sample_rate_in": RATE,
                "sample_rate_out": self.speaker.sample_rate,
            }
        )
        return True

    async def _receive(self) -> None:
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    if self.busy:
                        continue  # not listening while answering (see the module docstring)
                    for event in self.endpointer.feed(message["bytes"]):
                        if isinstance(event, str):
                            await self._send({"type": event})
                        else:
                            await self.work.put(event)
                elif message.get("text") is not None:
                    await self._control(json.loads(message["text"]))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await self.work.put(None)

    async def _control(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "stop":  # push-to-talk released
            audio = self.endpointer.flush()
            if audio is not None:
                await self.work.put(audio)
        elif kind == "interrupt":
            self.interrupted.set()
        elif kind == "approve":
            await self.work.put(bool(msg.get("approved")))
        else:
            await self._send({"type": "error", "code": "invalid_input", "message": f"Unknown message: {kind}"})

    # ---------- a turn ----------

    async def _turn(self, item: np.ndarray | bool | str) -> None:
        if isinstance(item, bool):
            return await self._answer_approval(item)
        if isinstance(item, str):  # a reminder
            await self._send({"type": "reminder", "text": item})
            return await self._say(item)
        await self._send({"type": "transcribing"})
        text = await asyncio.to_thread(stt.transcribe, item)
        if not text:
            await self._send({"type": "no_speech"})
            return
        await self._send({"type": "transcript", "text": text})
        if await asyncio.to_thread(lambda: self.chats.session(self.chat_id).waiting) is not None:
            if YES.match(text) or NO.match(text):
                return await self._answer_approval(bool(YES.match(text)))
            return await self._say("Please say yes or no to the change first.")
        self.chats.store.name_from_first_message(self.chat_id, text)
        self.chats.log(self.chat_id, "user", {"text": text, "voice": True})
        await self._agent(lambda s: s.stream(text))

    async def _answer_approval(self, approved: bool) -> None:
        if await asyncio.to_thread(lambda: self.chats.session(self.chat_id).waiting) is None:
            return await self._say("There is nothing waiting for approval.")
        self.chats.log(self.chat_id, "approval_answer", {"approved": approved})
        await self._send({"type": "approval_answer", "approved": approved})  # the app closes its card
        await self._agent(lambda s: s.resume(approved))

    async def _agent(self, run: Callable[..., Iterator]) -> None:
        """Run the agent in a thread; pass its events on as they come, and speak what matters."""
        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        def work() -> None:
            try:
                for event in self.chats.turn(self.chat_id, run, self.on_new_files):
                    loop.call_soon_threadsafe(events.put_nowait, event)
            finally:
                loop.call_soon_threadsafe(events.put_nowait, None)

        task = loop.run_in_executor(None, work)
        said_looking = False
        while (event := await events.get()) is not None:
            kind, data = event
            await self._send({"type": kind, **data})
            if kind == "tool_call" and not said_looking:
                said_looking = True
                await self._say(LOOKING)
            elif kind == "approval":
                await self._say(
                    f"I'd like to: {data.get('summary', 'make a change')}. Should I go ahead? Say yes or no."
                )
            elif kind == "answer":
                await self._say(data.get("text", ""))
            elif kind == "error":
                await self._say("Sorry, that didn't work. " + data.get("text", ""))
        await task

    async def _say(self, text: str) -> None:
        """Speak, sentence by sentence; stops at the next sentence or chunk when interrupted."""
        speaker = self.speaker
        assert speaker is not None
        for sentence in sentences(text):
            if self.interrupted.is_set():
                return
            await self._send({"type": "speaking", "text": sentence})
            audio = await asyncio.to_thread(lambda s=sentence: list(speaker.speak(s)))
            for chunk in audio:
                if self.interrupted.is_set():
                    await self._send({"type": "interrupted"})
                    return
                await self.ws.send_bytes(chunk)

    async def _send(self, event: dict) -> None:
        if self.ws.application_state == WebSocketState.CONNECTED:
            await self.ws.send_text(json.dumps(event))


def _warm_chat_model() -> None:
    """Load the chat model now and keep it, with the agent's own options so it isn't reloaded:
    a cold start takes ~12 s, which a spoken answer can't wait for."""
    if not registry.is_ollama("agent"):
        return
    try:
        import ollama

        ollama.Client(host=registry.get(settings.agent_provider)["base_url"]).generate(
            model=settings.agent_model,
            prompt="",
            keep_alive="30m",
            options=settings.ollama_options(num_ctx=settings.num_ctx),
        )
    except Exception as e:  # Ollama down: the first turn says so
        log.info("could not warm the chat model: %s", e)
