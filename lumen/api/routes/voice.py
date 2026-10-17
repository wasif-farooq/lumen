"""Real-time voice chat: one WebSocket per conversation (protocol in docs/VOICE.md)."""

from fastapi import APIRouter, WebSocket

from ...core import errors
from ..deps import who
from ..services import Services
from ..services.voice import VoiceCall

router = APIRouter()


@router.websocket("/api/voice")
async def voice(ws: WebSocket, chat_id: str | None = None) -> None:
    svc: Services = ws.app.state.services
    try:
        who(ws, svc)
    except errors.NotPaired:
        await ws.close(code=4401, reason="Not paired")
        return
    if chat_id is None:
        chat_id = str(svc.chats.store.create()["id"])
    elif svc.chats.store.title(chat_id) is None:
        await ws.close(code=4404, reason="No such chat")
        return
    await ws.accept()
    call = VoiceCall(ws, svc.chats, chat_id, svc.indexer.start)
    svc.reminders.speakers.append(call.announce)  # reminders are said while voice is on
    try:
        await call.run()
    finally:
        svc.reminders.speakers.remove(call.announce)
