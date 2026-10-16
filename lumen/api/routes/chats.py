"""Chats: history, sending a message (streamed), approving changes, undo."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ... import fileops
from ...core import errors
from ..deps import auth, services
from ..responses import ChatEventOut, ChatOut, Message, Ok, Pending
from ..schemas import Ask, Decision, NewChat, UndoReq
from ..services import Services

router = APIRouter(dependencies=[Depends(auth)])


@router.get("/api/chats")
def list_chats(svc: Services = Depends(services)) -> list[ChatOut]:
    return [ChatOut.model_validate(x) for x in svc.chats.store.recent()]


@router.post("/api/chats")
def create_chat(body: NewChat, svc: Services = Depends(services)) -> ChatOut:
    return ChatOut.model_validate(svc.chats.store.create(body.title))


@router.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, svc: Services = Depends(services)) -> Ok:
    svc.chats.store.delete(chat_id)
    svc.chats.sessions.pop(chat_id, None)
    return Ok(ok=True)


@router.get("/api/chats/{chat_id}/events")
def chat_events(chat_id: str, svc: Services = Depends(services)) -> list[ChatEventOut]:
    return [ChatEventOut.model_validate(x) for x in svc.chats.store.events(chat_id)]


@router.post("/api/chats/{chat_id}/messages")
def send_message(chat_id: str, body: Ask, svc: Services = Depends(services)) -> StreamingResponse:
    """Stream the agent's work as server-sent events (one JSON object per `data:` line)."""
    if svc.chats.store.title(chat_id) is None:
        raise errors.NotFound("No such chat")
    text = body.text.strip()
    if not text:
        raise errors.InvalidInput("Empty message")
    svc.chats.store.name_from_first_message(chat_id, text)
    svc.chats.log(chat_id, "user", {"text": text})
    return svc.chats.stream(chat_id, lambda s: s.stream(text), svc.indexer.start)


@router.post("/api/chats/{chat_id}/approve")
def approve(chat_id: str, body: Decision, svc: Services = Depends(services)) -> StreamingResponse:
    """Answer the agent's pending change request (Approve / Cancel) and stream what happens next."""
    if svc.chats.session(chat_id).waiting is None:
        raise errors.Conflict("Nothing is waiting for approval in this chat")
    svc.chats.log(chat_id, "approval_answer", {"approved": body.approved})
    return svc.chats.stream(chat_id, lambda s: s.resume(body.approved), svc.indexer.start)


@router.get("/api/chats/{chat_id}/pending")
def pending(chat_id: str, svc: Services = Depends(services)) -> Pending:
    return Pending(pending=svc.chats.session(chat_id).waiting)


@router.post("/api/actions/{action_id}/undo")
def undo_action(action_id: str, body: UndoReq, svc: Services = Depends(services)) -> Message:
    try:
        msg = fileops.undo(action_id)
    except (fileops.FileOpError, OSError) as e:
        raise errors.InvalidInput(str(e)) from e
    if body.chat_id:
        svc.chats.log(body.chat_id, "undone", {"action_id": action_id, "text": msg})
    return Message(ok=True, message=msg)


@router.get("/api/actions")
def actions() -> list[dict]:
    return list(reversed(fileops.history()))[:100]
