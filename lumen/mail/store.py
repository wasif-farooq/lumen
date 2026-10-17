"""Indexed mail (mail.db): each message, a full-text index of its text and attachments' text, and how
far each folder has been read."""

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from ..core.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, account TEXT NOT NULL, folder TEXT NOT NULL, uidvalidity INTEGER, uid INTEGER,
    message_id TEXT, sender TEXT, sender_name TEXT, recipients TEXT, subject TEXT, date REAL, size INTEGER,
    attachments TEXT NOT NULL DEFAULT '[]', UNIQUE (account, folder, uidvalidity, uid));
CREATE INDEX IF NOT EXISTS messages_account ON messages(account);
CREATE INDEX IF NOT EXISTS messages_msgid ON messages(account, message_id);
CREATE VIRTUAL TABLE IF NOT EXISTS mail_fts USING fts5(
    subject, people, body, attachments, kind, tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS folders (
    account TEXT NOT NULL, folder TEXT NOT NULL, uidvalidity INTEGER, last_uid INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account, folder));
"""
KIND = "email mail message"  # so "the email from the bank" matches mail without those words in it

# Changes to an existing mail.db, run once each in order; PRAGMA user_version records the last one
UPGRADES: list[Callable[[sqlite3.Connection], None]] = []


class MailStore:
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

    def rows(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # ---------- reading a folder ----------

    def folder_state(self, account: str, folder: str) -> tuple[int, int]:
        """(uidvalidity, last uid read) of a folder; (0, 0) when never read."""
        r = self.rows("SELECT uidvalidity, last_uid FROM folders WHERE account=? AND folder=?", (account, folder))
        return (r[0]["uidvalidity"] or 0, r[0]["last_uid"] or 0) if r else (0, 0)

    def set_folder_state(self, account: str, folder: str, uidvalidity: int, last_uid: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO folders (account, folder, uidvalidity, last_uid) VALUES (?,?,?,?) "
                "ON CONFLICT(account, folder) DO UPDATE SET "
                "uidvalidity=excluded.uidvalidity, last_uid=excluded.last_uid",
                (account, folder, uidvalidity, last_uid),
            )
            self._db.commit()

    def forget_folder(self, account: str, folder: str) -> None:
        """The folder's UIDs changed (UIDVALIDITY): drop what was indexed from it and read it again."""
        with self._lock:
            sql = "SELECT id FROM messages WHERE account=? AND folder=?"
            ids = [r["id"] for r in self._db.execute(sql, (account, folder))]
            self._delete(ids)
            self._db.execute("DELETE FROM folders WHERE account=? AND folder=?", (account, folder))
            self._db.commit()

    # ---------- messages ----------

    def has_message(self, account: str, message_id: str) -> bool:
        """Already indexed (the same mail in another folder, e.g. a Gmail label)."""
        return bool(message_id) and bool(
            self.rows("SELECT 1 FROM messages WHERE account=? AND message_id=? LIMIT 1", (account, message_id))
        )

    def add(self, account: str, folder: str, uidvalidity: int, uid: int, size: int, m: dict) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO messages (account, folder, uidvalidity, uid, message_id, sender, sender_name, "
                "recipients, subject, date, size, attachments) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (account, folder, uidvalidity, uid, m["message_id"], m["sender"], m["sender_name"], m["recipients"],
                 m["subject"], m["date"], size, json.dumps(m["attachments"])),
            )  # fmt: skip
            if not cur.lastrowid or cur.rowcount == 0:
                return 0
            people = f"{m['sender_name']} {m['sender']} {m['recipients']}"
            names = " ".join(a["name"] for a in m["attachments"])
            self._db.execute(
                "INSERT INTO mail_fts (rowid, subject, people, body, attachments, kind) VALUES (?,?,?,?,?,?)",
                (cur.lastrowid, m["subject"], people, m["text"], f"{names}\n{m['attachments_text']}", KIND),
            )
            self._db.commit()
            return cur.lastrowid

    def get(self, mail_id: int) -> dict | None:
        r = self.rows(
            "SELECT m.*, f.body, f.attachments AS attachments_text FROM messages m JOIN mail_fts f ON f.rowid = m.id "
            "WHERE m.id = ?",
            (mail_id,),
        )
        if not r:
            return None
        out = dict(r[0])
        out["attachments"] = json.loads(out["attachments"] or "[]")
        return out

    def count(self, account: str) -> int:
        return self.rows("SELECT COUNT(*) AS n FROM messages WHERE account=?", (account,))[0]["n"]

    def forget_account(self, account: str) -> None:
        with self._lock:
            ids = [r["id"] for r in self._db.execute("SELECT id FROM messages WHERE account=?", (account,))]
            self._delete(ids)
            self._db.execute("DELETE FROM folders WHERE account=?", (account,))
            self._db.commit()

    def _delete(self, ids: list[int]) -> None:
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            marks = ",".join("?" * len(chunk))
            self._db.execute(f"DELETE FROM mail_fts WHERE rowid IN ({marks})", chunk)
            self._db.execute(f"DELETE FROM messages WHERE id IN ({marks})", chunk)


_stores: dict[Path, MailStore] = {}
_stores_lock = threading.Lock()


def mail_store() -> MailStore:
    """mail.db in the current data folder (one connection per folder)."""
    path = settings.data_dir / "mail.db"
    with _stores_lock:
        if path not in _stores:
            _stores[path] = MailStore(path)
        return _stores[path]
