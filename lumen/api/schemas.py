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


# ---------- notes, to-dos, reminders ----------


class NoteIn(BaseModel):
    title: str
    text: str = ""
    tags: list[str] = []


class NoteChange(BaseModel):
    title: str | None = None
    text: str | None = None
    tags: list[str] | None = None


class ListIn(BaseModel):
    name: str


class TodoIn(BaseModel):
    text: str
    list_id: int | None = None
    list: str | None = None  # a list by name (made if missing), when there is no list_id
    notes: str = ""
    priority: int | str = 0
    due: str | None = None  # plain words ("Friday at 5")
    due_at: float | None = None


class TodoChange(BaseModel):
    text: str | None = None
    notes: str | None = None
    priority: int | str | None = None
    due: str | None = None
    due_at: float | None = None  # send null to clear the due time
    done: bool | None = None
    list_id: int | None = None
    position: int | None = None


class ReminderIn(BaseModel):
    text: str
    when: str | None = None  # plain words ("tomorrow at 5", "every Monday 9am")
    at: float | None = None
    repeat: str | None = None  # none | daily | weekdays | weekly | monthly (or taken from `when`)
    todo_id: int | None = None


class ReminderChange(BaseModel):
    text: str | None = None
    when: str | None = None
    at: float | None = None
    repeat: str | None = None


class Snooze(BaseModel):
    minutes: int = 10


class MailAccountIn(BaseModel):
    email: str
    password: str
    host: str = ""  # empty: guessed from the address
    port: int = 0
    security: str = ""
    user: str = ""  # empty: the address
    since_days: int = 365  # how far back to index
