"""The search index database: one SQLite file in the data folder, opened in WAL mode so the
server can read while the indexer writes."""

import sqlite3
import time

from ..core.filetypes import TEXT_EXTS
from ..core.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ext TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    has_text INTEGER NOT NULL DEFAULT 0,
    caption TEXT,  -- AI description of images/scans/videos; NULL = not done yet
    duration REAL,  -- seconds, for video/audio
    media_done INTEGER,  -- video/audio pass: NULL = pending, 1 = done, 0 = failed
    fingerprint TEXT  -- content id for media, to reuse work on identical copies
);
CREATE INDEX IF NOT EXISTS files_mtime ON files(mtime);
CREATE INDEX IF NOT EXISTS files_ext ON files(ext);
-- rowid = files.id
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    name, path, content,
    tokenize = 'unicode61 remove_diacritics 2'
);
-- timestamped transcript lines of video/audio, so a hit can jump to the right moment
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS segments_file ON segments(file_id);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text, tokenize = 'unicode61 remove_diacritics 2'
);
-- ~700-character passages of documents, for answering questions from the right part of a file
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    total INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS passages_file ON passages(file_id);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    text, extra, tokenize = 'unicode61 remove_diacritics 2'
);
"""

# Columns added after the first release; created on old databases by connect()
LATER_COLUMNS = {
    "caption": "TEXT",
    "duration": "REAL",
    "media_done": "INTEGER",
    "fingerprint": "TEXT",
    # visual search: CLIP signature (512 float32); visual_done NULL = pending
    "embedding": "BLOB",
    "visual_done": "INTEGER",
}


def _drop_image_hashes(conn: sqlite3.Connection) -> None:
    """dhash and sha1 were only used by the duplicate-image finder, removed in 0.1.1."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(files)")}
    for col in ("dhash", "sha1"):
        if col in have:
            conn.execute(f"ALTER TABLE files DROP COLUMN {col}")


def _reread_cut_short_documents(conn: sqlite3.Connection) -> None:
    """Until 0.2, text was read only from the first 100 PDF pages, the first 200,000 characters and
    files up to 25 MB, and spreadsheets, slides, OpenDocument files and e-books not at all. Mark
    those files changed so the next scan reads them again (scanned PDFs keep their descriptions)."""
    text = ",".join(f"'{e}'" for e in sorted(TEXT_EXTS | {"docx"}))
    conn.execute(
        "UPDATE files SET mtime = -1 WHERE ext IN ('xlsx','pptx','odt','ods','odp','epub') "
        "OR (ext = 'pdf' AND has_text = 1) "
        f"OR (ext IN ({text}) AND (size > 25 * 1024 * 1024 "
        "OR id IN (SELECT rowid FROM files_fts WHERE length(content) >= 199000)))"
    )


# Changes to an existing index, run once each in order; PRAGMA user_version records the last
# one done. New indexes run them too (each step only does what is still needed).
UPGRADES = [_drop_image_hashes, _reread_cut_short_documents]


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    _use_wal(conn)
    conn.executescript(SCHEMA)
    if _missing_columns(conn):
        # The server and the indexer can both open a new database at once: hold the write
        # lock while re-checking, so only one of them adds each column.
        conn.execute("BEGIN IMMEDIATE")
        for col in _missing_columns(conn):
            conn.execute(f"ALTER TABLE files ADD COLUMN {col} {LATER_COLUMNS[col]}")
        conn.commit()
    if _version(conn) < len(UPGRADES):
        conn.execute("BEGIN IMMEDIATE")  # as above: one process upgrades, the other then sees it done
        for step in UPGRADES[_version(conn) :]:
            step(conn)
        conn.execute(f"PRAGMA user_version={len(UPGRADES)}")
        conn.commit()
    return conn


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _use_wal(conn: sqlite3.Connection, attempts: int = 100) -> None:
    """Switch a new database to WAL (it is stored in the file, so later opens skip this).

    The switch needs the database to itself and SQLite does not wait for that, so when the server
    and the indexer open a brand-new index together, retry briefly instead of failing."""
    for _ in range(attempts):
        try:
            if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                conn.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e):
                raise
            time.sleep(0.05)
    raise sqlite3.OperationalError("database is locked (could not switch the index to WAL mode)")


def _missing_columns(conn: sqlite3.Connection) -> list[str]:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(files)")}
    return [col for col in LATER_COLUMNS if col not in have]
