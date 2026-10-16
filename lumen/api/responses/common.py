"""The base of every answer (extra fields allowed), and the small ones: ok, a message, deleted."""

from pydantic import BaseModel, ConfigDict


class Out(BaseModel):
    model_config = ConfigDict(extra="allow")


class Ok(Out):
    ok: bool = True


class Message(Out):
    ok: bool = True
    message: str


class Deleted(Out):
    deleted: str
