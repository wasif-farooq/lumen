"""Notes, to-do lists, to-dos and reminders (the laptop and paired phones)."""

import time
from datetime import datetime

from fastapi import APIRouter, Depends

from ... import planner
from ...core import errors
from ...planner import notes
from ...planner.times import describe, parse_when
from ..deps import auth
from ..responses import Deleted, ListOut, NoteOut, NoteSummary, ReminderOut, TodoOut
from ..schemas import ListIn, NoteChange, NoteIn, ReminderChange, ReminderIn, Snooze, TodoChange, TodoIn

router = APIRouter(dependencies=[Depends(auth)])


# ---------- notes ----------


@router.get("/api/notes")
def list_notes(q: str = "") -> list[NoteSummary]:
    return [NoteSummary.model_validate(n) for n in notes.list_notes(q)]


@router.post("/api/notes")
def create_note(body: NoteIn) -> NoteOut:
    return NoteOut.model_validate(notes.create(body.title, body.text, body.tags))


@router.get("/api/notes/{name:path}")
def get_note(name: str) -> NoteOut:
    return NoteOut.model_validate(notes.get(name))


@router.put("/api/notes/{name:path}")
def change_note(name: str, body: NoteChange) -> NoteOut:
    return NoteOut.model_validate(notes.update(name, body.title, body.text, body.tags))


@router.delete("/api/notes/{name:path}")
def trash_note(name: str) -> dict:
    """To the Trash; undo with /api/actions/{action_id}/undo."""
    return notes.trash(name)


# ---------- lists ----------


@router.get("/api/lists")
def lists() -> list[ListOut]:
    return [ListOut.model_validate(x) for x in planner.store().lists()]


@router.post("/api/lists")
def add_list(body: ListIn) -> ListOut:
    return ListOut.model_validate(planner.store().add_list(body.name))


@router.patch("/api/lists/{list_id}")
def rename_list(list_id: int, body: ListIn) -> ListOut:
    return ListOut.model_validate(planner.store().rename_list(list_id, body.name))


@router.delete("/api/lists/{list_id}")
def delete_list(list_id: int) -> Deleted:
    planner.store().delete_list(list_id)
    return Deleted(deleted=str(list_id))


# ---------- to-dos ----------


@router.get("/api/todos")
def todos(list_id: int | None = None, done: bool | None = False) -> list[TodoOut]:
    return [TodoOut.model_validate(t) for t in planner.store().todos(list_id, done)]


@router.post("/api/todos")
def add_todo(body: TodoIn) -> TodoOut:
    store = planner.store()
    list_id = body.list_id if body.list_id is not None else store.list_named(body.list or "", create=True)["id"]
    due_at = _time(body.due) if body.due else body.due_at
    return TodoOut.model_validate(store.add_todo(body.text, list_id, body.notes, body.priority, due_at))


@router.patch("/api/todos/{todo_id}")
def change_todo(todo_id: int, body: TodoChange) -> TodoOut:
    changes = {k: getattr(body, k) for k in body.model_fields_set if k != "due"}
    if body.due:
        changes["due_at"] = _time(body.due)
    return TodoOut.model_validate(planner.store().update_todo(todo_id, **changes))


@router.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: int) -> Deleted:
    planner.store().delete_todo(todo_id)
    return Deleted(deleted=str(todo_id))


# ---------- reminders ----------


@router.get("/api/reminders")
def reminders(all: bool = False) -> list[ReminderOut]:
    return [_reminder(r) for r in planner.store().reminders(None if all else True)]


@router.get("/api/reminders/due")
def due_reminders() -> list[ReminderOut]:
    """Reminders that went off and are waiting for the user (the app's banner)."""
    return [_reminder(r) for r in planner.store().waiting()]


@router.post("/api/reminders")
def add_reminder(body: ReminderIn) -> ReminderOut:
    at, repeat = _when(body.when, body.at, body.repeat)
    return _reminder(planner.store().add_reminder(body.text, at, repeat, body.todo_id))


@router.patch("/api/reminders/{reminder_id}")
def change_reminder(reminder_id: int, body: ReminderChange) -> ReminderOut:
    at, repeat = (None, body.repeat)
    if body.when or body.at is not None:
        at, repeat = _when(body.when, body.at, body.repeat)
    return _reminder(planner.store().update_reminder(reminder_id, body.text, at, repeat))


@router.delete("/api/reminders/{reminder_id}")
def cancel_reminder(reminder_id: int) -> ReminderOut:
    """Cancel (kept, so /restore can bring it back)."""
    return _reminder(planner.store().set_active(reminder_id, False))


@router.post("/api/reminders/{reminder_id}/restore")
def restore_reminder(reminder_id: int) -> ReminderOut:
    return _reminder(planner.store().set_active(reminder_id, True))


@router.post("/api/reminders/{reminder_id}/snooze")
def snooze_reminder(reminder_id: int, body: Snooze) -> ReminderOut:
    if not 1 <= body.minutes <= 24 * 60:
        raise errors.InvalidInput("Snooze for 1 minute to 24 hours.")
    return _reminder(planner.store().snooze(reminder_id, time.time() + body.minutes * 60))


@router.post("/api/reminders/{reminder_id}/ack")
def acknowledge_reminder(reminder_id: int) -> ReminderOut:
    return _reminder(planner.store().acknowledge(reminder_id))


# ---------- helpers ----------


HINT = "Try e.g. “tomorrow at 5pm”, “Friday 9:30” or “every Monday 9am”."


def _time(words: str) -> float:
    w = parse_when(words, datetime.now())
    if w is None:
        raise errors.InvalidInput(f"I couldn't tell when “{words}” is.", HINT)
    return w.at.timestamp()


def _when(words: str | None, at: float | None, repeat: str | None) -> tuple[float, str]:
    """A reminder's first time and repeat, from plain words or a time (repeat given wins)."""
    if words:
        w = parse_when(words, datetime.now())
        if w is None:
            raise errors.InvalidInput(f"I couldn't tell when “{words}” is.", HINT)
        at_time, repeat = w.at.timestamp(), repeat or w.repeat
    elif at is not None:
        at_time, repeat = at, repeat or "none"
    else:
        raise errors.InvalidInput("Say when: `when` (plain words) or `at` (a time).")
    if repeat == "none" and at_time <= time.time():
        raise errors.InvalidInput("That time has already passed.")
    return at_time, repeat


def _reminder(r: dict) -> ReminderOut:
    now = datetime.now()
    shown = r["next_at"] if r["next_at"] is not None else r["at"]
    return ReminderOut.model_validate(
        {
            **r,
            "acknowledged": bool(r["acknowledged"]),
            "active": bool(r["active"]),
            "when": describe(datetime.fromtimestamp(shown), r["repeat"], now),
        }
    )
