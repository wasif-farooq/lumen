"""Real-time voice chat over /api/voice, with fake speech models (no audio hardware, no downloads)."""

import json
import sys

import pytest
from conftest import pcm, tool_call
from langchain_core.messages import AIMessage
from starlette.websockets import WebSocketDisconnect


def say(ws, *parts: bytes, chunk_ms: int = 100) -> None:
    """Stream microphone audio in small chunks, as an app would."""
    data = b"".join(parts)
    step = 16000 * 2 * chunk_ms // 1000
    for i in range(0, len(data), step):
        ws.send_bytes(data[i : i + step])


def until_turn_done(ws) -> tuple[list[dict], int]:
    """The events of one turn, and how many bytes of speech came back."""
    events, audio = [], 0
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            audio += len(message["bytes"])
            continue
        event = json.loads(message["text"])
        events.append(event)
        if event["type"] == "turn_done":
            return events, audio


def types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def ready(ws) -> dict:
    event = json.loads(ws.receive_text())
    assert event["type"] == "ready", event
    return event


def test_a_spoken_question_gets_a_spoken_answer_and_is_kept_in_the_chat(indexed, local, model, voice):
    voice.heard = ["where is my invoice"]
    model.script = [
        tool_call("search_files", query="invoice"),
        AIMessage(content="Found it: **invoice-1042.pdf** in `/home/alex/Documents/invoice-1042.pdf`. It is 250 EUR."),
    ]
    with local.websocket_connect("/api/voice") as ws:
        hello = ready(ws)
        assert hello["sample_rate_in"] == 16000 and hello["sample_rate_out"] == 22050
        say(ws, pcm(0.5, loud=False), pcm(1.0, loud=True), pcm(1.0, loud=False))  # silence ends the question
        events, audio = until_turn_done(ws)

    order = types(events)
    for step in ["speech_start", "transcribing", "transcript", "tool_call", "results", "answer", "turn_done"]:
        assert step in order, (step, order)
    assert order.index("transcript") < order.index("tool_call") < order.index("answer")
    assert events[order.index("transcript")]["text"] == "where is my invoice"
    # "One moment." while it searches, then the answer read without markdown or the full path
    assert voice.spoken == ["One moment.", "Found it: invoice-1042.pdf in invoice-1042.pdf.", "It is 250 EUR."]
    assert audio > 0

    history = local.get(f"/api/chats/{hello['chat_id']}/events").json()
    assert history[0]["type"] == "user" and history[0]["text"] == "where is my invoice" and history[0]["voice"] is True
    assert history[-1]["type"] == "answer"
    assert local.get("/api/chats").json()[0]["title"] == "where is my invoice"


def test_push_to_talk_ends_the_question_when_released(env, local, model, voice):
    voice.heard = ["hello"]
    model.script = [AIMessage(content="Hi there.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.3, loud=False), pcm(0.6, loud=True))  # no silence after it
        ws.send_text(json.dumps({"type": "stop"}))
        events, _ = until_turn_done(ws)
    assert events[types(events).index("transcript")]["text"] == "hello"
    assert voice.spoken == ["Hi there."]


def test_noise_that_was_not_speech_is_ignored(env, local, model, voice):
    voice.heard = [""]  # the speech model heard no words in it
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.5, loud=True), pcm(1.0, loud=False))
        events, audio = until_turn_done(ws)
    assert "no_speech" in types(events) and "answer" not in types(events) and audio == 0
    assert model.seen == []  # the chat model was never asked


def test_interrupting_stops_the_answer(env, local, model, voice):
    voice.heard = ["tell me everything"]
    voice.seconds_per_sentence = 0.3
    model.script = [AIMessage(content="One. Two. Three. Four. Five. Six.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        while json.loads(ws.receive_text())["type"] != "speaking":
            pass
        ws.send_text(json.dumps({"type": "interrupt"}))  # while the first sentence is being said
        events, _ = until_turn_done(ws)
    assert 1 <= len(voice.spoken) < 6  # stopped before the end
    assert "turn_done" in types(events)


def test_a_change_waits_for_a_spoken_yes(env, local, model, voice):
    target = env.documents / "Invoices"
    voice.heard = ["make a folder for invoices", "yes please"]
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="Created the folder.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        first, _ = until_turn_done(ws)
        assert "approval" in types(first) and not target.exists()
        assert voice.spoken[-2:] == ["Should I go ahead?", "Say yes or no."]  # after what it wants to do
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        second, _ = until_turn_done(ws)
    assert "action_done" in types(second) and target.is_dir()
    assert {"type": "approval_answer", "approved": True} in second  # so the app closes its card
    assert voice.spoken[-1] == "Created the folder."


def test_a_spoken_no_cancels_the_change(env, local, model, voice):
    target = env.documents / "Taxes"
    voice.heard = ["make a taxes folder", "no thanks"]
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="OK, I won't.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        until_turn_done(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        events, _ = until_turn_done(ws)
    assert "action_cancelled" in types(events) and not target.exists()


def test_its_own_voice_from_the_speakers_is_not_taken_as_a_question(env, local, model, voice):
    voice.heard = ["what is new", "this should never be heard"]
    voice.seconds_per_sentence = 0.2
    model.script = [AIMessage(content="Nothing much. All quiet. Have a nice day.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        while json.loads(ws.receive_text())["type"] != "speaking":
            pass
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))  # the answer, picked up by the microphone
        until_turn_done(ws)
    assert voice.transcriptions == 1


def test_the_app_can_also_answer_a_change_with_a_button(env, local, model, voice):
    target = env.documents / "Receipts"
    voice.heard = ["make a receipts folder"]
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="OK, not doing it.")]
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        until_turn_done(ws)
        ws.send_text(json.dumps({"type": "approve", "approved": False}))
        events, _ = until_turn_done(ws)
    assert "action_cancelled" in types(events) and not target.exists()


def test_voice_continues_an_existing_chat(env, local, model, voice):
    chat = local.post("/api/chats", json={}).json()["id"]
    voice.heard = ["and the soup?"]
    model.script = [AIMessage(content="Lentils.")]
    with local.websocket_connect(f"/api/voice?chat_id={chat}") as ws:
        assert ready(ws)["chat_id"] == chat
        say(ws, pcm(0.6, loud=True), pcm(1.0, loud=False))
        until_turn_done(ws)
    assert local.get(f"/api/chats/{chat}/events").json()[-1]["text"] == "Lentils."


def test_only_the_laptop_and_paired_phones_can_talk(env, local, remote, voice):
    with pytest.raises(WebSocketDisconnect) as refused, remote.websocket_connect("/api/voice") as ws:
        ws.receive_text()
    assert refused.value.code == 4401
    code = local.post("/api/pair/start").json()["code"]
    token = remote.post("/api/pair", json={"code": code, "name": "phone"}).json()["token"]
    with remote.websocket_connect(f"/api/voice?token={token}") as ws:  # a WebSocket can't always set headers
        ready(ws)
    with pytest.raises(WebSocketDisconnect) as missing, local.websocket_connect("/api/voice?chat_id=nope") as ws:
        ws.receive_text()
    assert missing.value.code == 4404


def test_without_the_speech_engine_voice_says_how_to_install_it(env, local, monkeypatch):
    monkeypatch.setitem(sys.modules, "piper", None)  # as if the voice extra weren't installed
    with local.websocket_connect("/api/voice") as ws:
        event = json.loads(ws.receive_text())
    assert event["type"] == "error" and event["code"] == "voice_unavailable"
    assert "uv sync --extra voice" in event["hint"]
    assert not (env.data / "models" / "piper").exists()  # nothing was downloaded
    assert local.get("/api/status").json()["voice"] is False  # so the app doesn't offer it


def test_the_status_says_voice_can_run(env, local, voice):
    assert local.get("/api/status").json()["voice"] is True


def test_room_noise_and_a_silent_microphone_are_not_speech(env, local, model, real_voice_detector):
    import numpy as np

    rng = np.random.default_rng(3)
    with local.websocket_connect("/api/voice") as ws:
        ready(ws)
        # a muted or warming-up microphone (exact zeros), then a quiet room: this once made a
        # loudness-based detector take noise for speech, and the question never ended
        say(ws, np.zeros(16000, "<i2").tobytes(), rng.normal(0, 150, 3 * 16000).astype("<i2").tobytes())
        ws.send_text(json.dumps({"type": "stop"}))  # push-to-talk released: is there anything to hear?
        ws.send_text(json.dumps({"type": "nonsense"}))  # answered at once, so the test knows the server caught up
        assert json.loads(ws.receive_text())["code"] == "invalid_input"
    assert real_voice_detector.transcriptions == 0  # nothing was taken for speech
