"""Chats for the app: the history it shows, one agent session per chat, and streaming a turn."""

import json
import logging
import threading
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from fastapi.responses import StreamingResponse

from ...core.settings import settings
from ...storage.chats import ChatStore, checkpointer

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite import SqliteSaver

    from ...agent import Session

log = logging.getLogger(__name__)


class Chats:
    def __init__(self) -> None:
        self._store: ChatStore | None = None
        self._memory = None
        self.sessions: dict = {}  # chat id -> agent Session
        self.model_lock = threading.Lock()  # one local model: answer one chat at a time

    @property
    def store(self) -> ChatStore:
        if self._store is None:
            self._store = ChatStore(settings.data_dir / "chats.db")
        return self._store

    def memory(self) -> "SqliteSaver":
        """The agent's memory of each conversation."""
        if self._memory is None:
            self._memory = checkpointer(settings.data_dir / "memory.db")
        return self._memory

    def session(self, chat_id: str) -> "Session":
        from ...agent import Session

        if chat_id not in self.sessions:
            self.sessions[chat_id] = Session(thread_id=chat_id, checkpointer=self.memory(), app=True)
        return self.sessions[chat_id]

    def forget_sessions(self) -> None:
        """New sessions pick up changed settings (model, folders, CPU/GPU) on their next message."""
        self.sessions.clear()

    def log(self, chat_id: str, kind: str, data: dict) -> None:
        self.store.log(chat_id, kind, data)

    def turn(
        self, chat_id: str, run: Callable[..., Iterator], on_new_files: Callable[[], None]
    ) -> Iterator[tuple[str, dict]]:
        """Run one turn of the agent and yield its events as (type, data), recorded in the chat
        history as they happen. `run(session)` starts the turn: a message, or an approval answer.
        `on_new_files` runs when the turn created or copied files (they need indexing).
        Used by typed chat (as server-sent events) and by voice chat."""
        reindex = False
        with self.model_lock:
            try:
                for kind, payload in run(self.session(chat_id)):
                    if kind == "tool_call":
                        event = ("tool_call", {"name": payload[0], "args": payload[1]})
                    elif kind == "ui":
                        if (
                            payload["type"] == "action_done"
                            and not payload.get("dry_run")
                            and payload.get("op") != "move"
                        ):
                            reindex = True  # new files from a copy/create: index them
                        event = (payload["type"], {k: v for k, v in payload.items() if k != "type"})
                    elif kind == "approval":
                        event = ("approval", {k: v for k, v in payload.items() if k != "type"})
                    elif kind == "answer":
                        event = ("answer", {"text": payload or ""})
                    else:
                        continue
                    self.log(chat_id, *event)
                    yield event
            except Exception as e:  # loop limit, Ollama down, …: tell the UI instead of dropping the turn
                log.exception("chat %s: the turn failed", chat_id)
                self.log(chat_id, "error", {"text": friendly(e)})
                yield "error", {"text": friendly(e)}
        if reindex:
            on_new_files()

    def stream(self, chat_id: str, run: Callable[..., Iterator], on_new_files: Callable[[], None]) -> StreamingResponse:
        """A turn as server-sent events (one JSON object per `data:` line), for typed chat."""

        def events() -> Iterator[str]:
            yield f"data: {json.dumps({'type': 'started'})}\n\n"
            for kind, data in self.turn(chat_id, run, on_new_files):
                yield f"data: {json.dumps({'type': kind, **data})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def friendly(e: Exception) -> str:
    name = type(e).__name__
    if name == "GraphRecursionError":
        return "I went in circles on that one and stopped. Try rephrasing it more specifically."
    if isinstance(e, ConnectionError) or "connect" in str(e).lower():
        return f"Can't reach the local model (Ollama at {settings.ollama_host}). Is it running?"
    return f"Something went wrong: {e}"
