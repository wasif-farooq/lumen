"""Request bodies the API accepts."""

from pydantic import BaseModel


class NewChat(BaseModel):
    title: str | None = None


class Ask(BaseModel):
    text: str


class Decision(BaseModel):
    approved: bool


class UndoReq(BaseModel):
    chat_id: str | None = None


class SimilarReq(BaseModel):
    path: str


class OpenReq(BaseModel):
    path: str
    start_seconds: float = 0


class PathBody(BaseModel):
    path: str
    reindex: bool = False


class PullReq(BaseModel):
    model: str


class RoleReq(BaseModel):
    role: str
    provider: str = "local"
    model: str


class CheckReq(BaseModel):
    role: str
    provider: str
    model: str


class PairReq(BaseModel):
    code: str
    name: str = "Phone"
