"""Answers about chats."""

from .common import Out


class ChatOut(Out):
    id: str
    title: str
    created: float
    updated: float


class ChatEventOut(Out):
    """One thing in a conversation (user, tool_call, results, answer, approval…); its other
    fields depend on the type."""

    type: str
    at: float | None = None


class Pending(Out):
    pending: dict | None
