"""Reminders' part of the planner store (planner.db): add, change, cancel, snooze, and what the
reminder thread and the app's banner ask for."""

import time
from typing import TYPE_CHECKING

from ..core import errors
from .times import REPEATS


class ReminderStore:
    """Mixed into PlannerStore, which owns the connection, the lock and the to-dos."""

    if TYPE_CHECKING:

        def _rows(self, sql: str, args: tuple = ()) -> list[dict]: ...
        def _write(self, sql: str, args: tuple = ()) -> int: ...
        def get_todo(self, todo_id: int) -> dict: ...

    def reminders(self, active: bool | None = True) -> list[dict]:
        if active is None:
            return self._rows("SELECT * FROM reminders ORDER BY COALESCE(next_at, at)")
        return self._rows(
            "SELECT * FROM reminders WHERE active = ? ORDER BY COALESCE(next_at, at)", (1 if active else 0,)
        )

    def get_reminder(self, reminder_id: int) -> dict:
        rows = self._rows("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        if not rows:
            raise errors.NotFound("No such reminder.")
        return rows[0]

    def add_reminder(self, text: str, at: float, repeat: str = "none", todo_id: int | None = None) -> dict:
        text = text.strip()
        if not text:
            raise errors.InvalidInput("A reminder needs some text.")
        if repeat not in REPEATS:
            raise errors.InvalidInput(f"Repeat must be one of: {', '.join(REPEATS)}.")
        if todo_id is not None:
            self.get_todo(todo_id)
        new = self._write(
            "INSERT INTO reminders (todo_id, text, at, repeat, next_at, created) VALUES (?, ?, ?, ?, ?, ?)",
            (todo_id, text, at, repeat, at, time.time()),
        )
        return self.get_reminder(new)

    def update_reminder(self, reminder_id: int, text: str | None = None, at: float | None = None,
                        repeat: str | None = None) -> dict:  # fmt: skip
        r = self.get_reminder(reminder_id)
        if repeat is not None and repeat not in REPEATS:
            raise errors.InvalidInput(f"Repeat must be one of: {', '.join(REPEATS)}.")
        text = r["text"] if text is None else text.strip()
        if not text:
            raise errors.InvalidInput("A reminder needs some text.")
        at = r["at"] if at is None else at
        self._write(
            "UPDATE reminders SET text = ?, at = ?, repeat = ?, next_at = ?, active = 1 WHERE id = ?",
            (text, at, repeat or r["repeat"], at if at != r["at"] else r["next_at"] or at, reminder_id),
        )
        return self.get_reminder(reminder_id)

    def set_active(self, reminder_id: int, active: bool) -> dict:
        """Cancel (inactive) or bring back a reminder; cancelling also clears it from the banner."""
        self.get_reminder(reminder_id)
        if active:
            self._write("UPDATE reminders SET active = 1 WHERE id = ?", (reminder_id,))
        else:
            self._write("UPDATE reminders SET active = 0, acknowledged = 1 WHERE id = ?", (reminder_id,))
        return self.get_reminder(reminder_id)

    def snooze(self, reminder_id: int, until: float) -> dict:
        self.get_reminder(reminder_id)
        self._write("UPDATE reminders SET next_at = ?, active = 1, acknowledged = 1 WHERE id = ?", (until, reminder_id))
        return self.get_reminder(reminder_id)

    def acknowledge(self, reminder_id: int) -> dict:
        self.get_reminder(reminder_id)
        self._write("UPDATE reminders SET acknowledged = 1 WHERE id = ?", (reminder_id,))
        return self.get_reminder(reminder_id)

    def due(self, now: float) -> list[dict]:
        """Active reminders whose time has come."""
        return self._rows("SELECT * FROM reminders WHERE active = 1 AND next_at <= ? ORDER BY next_at", (now,))

    def fired(self, reminder_id: int, now: float, next_at: float | None) -> None:
        """Record that a reminder went off; one-off reminders end, repeating ones move on."""
        self._write(
            "UPDATE reminders SET last_fired = ?, acknowledged = 0, next_at = ?, active = ? WHERE id = ?",
            (now, next_at, 1 if next_at is not None else 0, reminder_id),
        )

    def waiting(self) -> list[dict]:
        """Reminders that went off and nobody has dealt with yet (the app's banner)."""
        return self._rows("SELECT * FROM reminders WHERE acknowledged = 0 ORDER BY last_fired")
