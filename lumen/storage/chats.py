"""Chat history for the app (chats and what happened in them) and the agent's memory.

The history is what the app shows; the agent's own memory of a conversation is kept separately by
LangGraph's checkpointer in memory.db.
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, chat_id TEXT, at REAL, type TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS events_chat ON events(chat_id);
"""
NEW_TITLE = "New chat"


class ChatStore:
    """Chats and their events in chats.db."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def recent(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute("SELECT * FROM chats ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create(self, title: str | None = None) -> dict:
        now = time.time()
        chat = {"id": str(uuid.uuid4()), "title": title or NEW_TITLE, "created": now, "updated": now}
        self._db.execute("INSERT INTO chats VALUES (:id, :title, :created, :updated)", chat)
        self._db.commit()
        return chat

    def delete(self, chat_id: str):
        self._db.execute("DELETE FROM events WHERE chat_id=?", (chat_id,))
        self._db.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        self._db.commit()

    def title(self, chat_id: str) -> str | None:
        """The chat's title, or None when there is no such chat."""
        row = self._db.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()
        return row["title"] if row else None

    def set_title(self, chat_id: str, title: str):
        self._db.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))
        self._db.commit()

    def name_from_first_message(self, chat_id: str, text: str, limit: int = 48):
        """A new chat is named after the first thing the user asked."""
        if self.title(chat_id) == NEW_TITLE:
            self.set_title(chat_id, text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "…")

    def log(self, chat_id: str, kind: str, data: dict):
        now = time.time()
        self._db.execute(
            "INSERT INTO events (chat_id, at, type, data) VALUES (?,?,?,?)", (chat_id, now, kind, json.dumps(data))
        )
        self._db.execute("UPDATE chats SET updated=? WHERE id=?", (now, chat_id))
        self._db.commit()

    def events(self, chat_id: str) -> list[dict]:
        rows = self._db.execute("SELECT type, data, at FROM events WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
        return [{"type": r["type"], "at": r["at"], **json.loads(r["data"])} for r in rows]


def checkpointer(path: Path):
    """LangGraph's store for the agent's memory of each conversation."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
