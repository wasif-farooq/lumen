"""To-do lists, to-dos and reminders in planner.db (notes are Markdown files: see notes.py;
reminders' part of the store: reminders.py).

Times are seconds since the epoch. One connection, shared by API requests and the reminder
thread, so every call holds a lock.
"""

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..core import errors
from .reminders import ReminderStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, position INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL REFERENCES lists(id), text TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 0, due_at REAL, done_at REAL,
    position INTEGER, created REAL, updated REAL);
CREATE INDEX IF NOT EXISTS todos_list ON todos(list_id);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY, todo_id INTEGER REFERENCES todos(id), text TEXT NOT NULL,
    at REAL NOT NULL, repeat TEXT NOT NULL DEFAULT 'none', next_at REAL, last_fired REAL,
    acknowledged INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, created REAL);
CREATE INDEX IF NOT EXISTS reminders_next ON reminders(active, next_at);
"""
DEFAULT_LIST = "To-do"
PRIORITIES = {"none": 0, "low": 1, "medium": 2, "normal": 2, "high": 3, "urgent": 3, "important": 3}


def _first_list(db: sqlite3.Connection) -> None:
    if not db.execute("SELECT 1 FROM lists").fetchone():
        db.execute("INSERT INTO lists (name, position, created) VALUES (?, 0, ?)", (DEFAULT_LIST, time.time()))


# Changes to an existing planner.db, run once each in order; PRAGMA user_version records the last one
UPGRADES: list[Callable[[sqlite3.Connection], None]] = [_first_list]


class PlannerStore(ReminderStore):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        for step in UPGRADES[version:]:
            step(self._db)
        self._db.execute(f"PRAGMA user_version={len(UPGRADES)}")
        self._db.commit()

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _write(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.lastrowid or 0

    # ---------- lists ----------

    def lists(self) -> list[dict]:
        return self._rows(
            "SELECT l.*, (SELECT COUNT(*) FROM todos t WHERE t.list_id = l.id AND t.done_at IS NULL) AS open "
            "FROM lists l ORDER BY position, id"
        )

    def list_named(self, name: str, create: bool = False) -> dict:
        """A list by name (any case); with create, a missing one is made."""
        name = name.strip() or DEFAULT_LIST
        with self._lock:
            rows = self._rows("SELECT * FROM lists WHERE name = ?", (name,))
            if rows:
                return rows[0]
            if not create:
                raise errors.NotFound(f"No list called “{name}”.")
            return self.add_list(name)

    def get_list(self, list_id: int) -> dict:
        rows = self._rows("SELECT * FROM lists WHERE id = ?", (list_id,))
        if not rows:
            raise errors.NotFound("No such list.")
        return rows[0]

    def add_list(self, name: str) -> dict:
        name = name.strip()
        if not name:
            raise errors.InvalidInput("A list needs a name.")
        with self._lock:
            if self._rows("SELECT 1 FROM lists WHERE name = ?", (name,)):
                raise errors.Conflict(f"There is already a list called “{name}”.")
            position = self._rows("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM lists")[0]["p"]
            new = self._write(
                "INSERT INTO lists (name, position, created) VALUES (?, ?, ?)", (name, position, time.time())
            )
            return self.get_list(new)

    def rename_list(self, list_id: int, name: str) -> dict:
        self.get_list(list_id)
        name = name.strip()
        if not name:
            raise errors.InvalidInput("A list needs a name.")
        with self._lock:
            if self._rows("SELECT 1 FROM lists WHERE name = ? AND id != ?", (name, list_id)):
                raise errors.Conflict(f"There is already a list called “{name}”.")
            self._write("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
        return self.get_list(list_id)

    def delete_list(self, list_id: int) -> None:
        """Only an empty list (done to-dos go with it); the last list stays."""
        self.get_list(list_id)
        with self._lock:
            if self._rows("SELECT 1 FROM todos WHERE list_id = ? AND done_at IS NULL", (list_id,)):
                raise errors.Conflict("This list still has to-dos. Finish or move them first.")
            if len(self.lists()) == 1:
                raise errors.Conflict("Keep at least one list.")
            done = [r["id"] for r in self._rows("SELECT id FROM todos WHERE list_id = ?", (list_id,))]
            for todo_id in done:
                self._db.execute("UPDATE reminders SET todo_id = NULL WHERE todo_id = ?", (todo_id,))
            self._db.execute("DELETE FROM todos WHERE list_id = ?", (list_id,))
            self._write("DELETE FROM lists WHERE id = ?", (list_id,))

    # ---------- to-dos ----------

    def todos(self, list_id: int | None = None, done: bool | None = False) -> list[dict]:
        where, args = [], []
        if list_id is not None:
            where.append("t.list_id = ?")
            args.append(list_id)
        if done is not None:
            where.append("t.done_at IS NOT NULL" if done else "t.done_at IS NULL")
        sql = "SELECT t.*, l.name AS list FROM todos t JOIN lists l ON l.id = t.list_id"
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self._rows(sql + " ORDER BY l.position, t.position, t.id", tuple(args))

    def get_todo(self, todo_id: int) -> dict:
        rows = self._rows(
            "SELECT t.*, l.name AS list FROM todos t JOIN lists l ON l.id = t.list_id WHERE t.id = ?", (todo_id,)
        )
        if not rows:
            raise errors.NotFound("No such to-do.")
        return rows[0]

    def add_todo(
        self, text: str, list_id: int, notes: str = "", priority: int | str = 0, due_at: float | None = None
    ) -> dict:
        text = text.strip()
        if not text:
            raise errors.InvalidInput("A to-do needs some text.")
        self.get_list(list_id)
        with self._lock:
            position = self._rows(
                "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM todos WHERE list_id = ?", (list_id,)
            )[0]["p"]
            now = time.time()
            new = self._write(
                "INSERT INTO todos (list_id, text, notes, priority, due_at, position, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (list_id, text, notes, _priority(priority), due_at, position, now, now),
            )
        return self.get_todo(new)

    def update_todo(self, todo_id: int, **changes: object) -> dict:
        """Change text, notes, priority, due_at, done (True/False), list_id or position."""
        todo = self.get_todo(todo_id)
        allowed = {"text", "notes", "priority", "due_at", "done", "list_id", "position"}
        if unknown := set(changes) - allowed:
            raise errors.InvalidInput(f"Can't change {', '.join(sorted(unknown))} of a to-do.")
        with self._lock:
            sets: dict[str, object] = {}
            if "text" in changes:
                text = str(changes["text"] or "").strip()
                if not text:
                    raise errors.InvalidInput("A to-do needs some text.")
                sets["text"] = text
            if "notes" in changes:
                sets["notes"] = str(changes["notes"] or "")
            if "priority" in changes:
                sets["priority"] = _priority(changes["priority"])
            if "due_at" in changes:
                sets["due_at"] = changes["due_at"]
            if "done" in changes:
                sets["done_at"] = (todo["done_at"] or time.time()) if changes["done"] else None
            if changes.get("list_id") is not None and changes["list_id"] != todo["list_id"]:
                self.get_list(int(changes["list_id"]))  # type: ignore[arg-type]
                sets["list_id"] = changes["list_id"]
                sets["position"] = self._rows(
                    "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM todos WHERE list_id = ?", (changes["list_id"],)
                )[0]["p"]
            if sets:
                sets["updated"] = time.time()
                cols = ", ".join(f"{k} = ?" for k in sets)
                self._write(f"UPDATE todos SET {cols} WHERE id = ?", (*sets.values(), todo_id))
            if changes.get("position") is not None:
                self._move(todo_id, int(changes["position"]))  # type: ignore[arg-type]
        return self.get_todo(todo_id)

    def _move(self, todo_id: int, position: int) -> None:
        """Put a to-do at a place in its list; the others close up around it."""
        todo = self.get_todo(todo_id)
        others = [r["id"] for r in self._rows(
            "SELECT id FROM todos WHERE list_id = ? AND id != ? ORDER BY position, id", (todo["list_id"], todo_id)
        )]  # fmt: skip
        others.insert(max(0, min(position, len(others))), todo_id)
        with self._lock:
            for i, tid in enumerate(others):
                self._db.execute("UPDATE todos SET position = ? WHERE id = ?", (i, tid))
            self._db.commit()

    def delete_todo(self, todo_id: int) -> dict:
        todo = self.get_todo(todo_id)
        with self._lock:
            self._db.execute("UPDATE reminders SET active = 0 WHERE todo_id = ?", (todo_id,))
            self._write("DELETE FROM todos WHERE id = ?", (todo_id,))
        return todo


def _priority(value: object) -> int:
    """0-3, from a number or a word ("high", "urgent", "low")."""
    if isinstance(value, str):
        word = value.strip().lower()
        if word.isdigit():
            value = int(word)
        elif word in PRIORITIES:
            return PRIORITIES[word]
        elif not word:
            return 0
        else:
            raise errors.InvalidInput(f"Priority must be low, medium, high or 0-3, not “{value}”.")
    try:
        n = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError) as e:
        raise errors.InvalidInput("Priority must be 0-3.") from e
    if not 0 <= n <= 3:
        raise errors.InvalidInput("Priority must be 0-3.")
    return n
