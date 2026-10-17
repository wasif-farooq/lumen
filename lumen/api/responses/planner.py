"""Notes, to-do lists, to-dos and reminders."""

from .common import Out


class NoteSummary(Out):
    name: str  # the file, relative to the notes folder
    title: str
    tags: list[str]
    created: str
    updated: str
    preview: str


class NoteOut(Out):
    name: str
    path: str
    title: str
    text: str
    tags: list[str]
    created: str
    updated: str
    action_id: str | None = None  # undo with /api/actions/{id}/undo


class ListOut(Out):
    id: int
    name: str
    position: int
    open: int = 0  # to-dos not done yet


class TodoOut(Out):
    id: int
    list_id: int
    list: str
    text: str
    notes: str
    priority: int  # 0 none, 1 low, 2 medium, 3 high
    due_at: float | None
    done_at: float | None
    position: int


class ReminderOut(Out):
    id: int
    todo_id: int | None
    text: str
    at: float
    repeat: str
    next_at: float | None  # when it goes off next (None: done)
    last_fired: float | None
    acknowledged: bool
    active: bool
    when: str  # for people: "tomorrow at 17:00, every week"
