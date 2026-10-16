"""The catalog of indexed files: removing files, counts, and what the index knows about a file.
Nothing here touches the files themselves."""

import os
from pathlib import Path

from ..core.settings import settings
from .db import connect


def drop_segments(conn, file_id: int):
    """A file's timestamped transcript lines."""
    conn.execute("DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (file_id,))
    conn.execute("DELETE FROM segments WHERE file_id=?", (file_id,))


def drop_derived(conn, file_id: int):
    """Everything derived from a file's contents: transcript lines and document passages."""
    from ..search import passages

    drop_segments(conn, file_id)
    passages.drop_file(conn, file_id)


def delete_file(conn, file_id: int):
    """Drop one file and everything derived from it from the index."""
    conn.execute("DELETE FROM files WHERE id=?", (file_id,))
    conn.execute("DELETE FROM files_fts WHERE rowid=?", (file_id,))
    drop_derived(conn, file_id)


def forget(path: str) -> int:
    """Drop a file, or every file under a folder, from the index. Returns how many."""
    path = str(Path(path).expanduser().resolve())
    conn = connect()
    try:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM files WHERE path = ? OR substr(path, 1, ?) = ?", (path, len(path) + 1, path + os.sep)
            )
        ]
        for file_id in ids:
            delete_file(conn, file_id)
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def stats() -> dict:
    conn = connect()
    try:
        total, with_text, captioned = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(has_text),0), COUNT(NULLIF(caption,'')) FROM files"
        ).fetchone()
        media = conn.execute("SELECT COUNT(*) FROM files WHERE media_done=1").fetchone()[0]
        visual = conn.execute("SELECT COUNT(*) FROM files WHERE visual_done=1").fetchone()[0]
        segments = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        return {
            "files": total,
            "with_text": with_text,
            "captioned": captioned,
            "media_indexed": media,
            "transcript_lines": segments,
            "visual_indexed": visual,
            "db": str(settings.db_path),
        }
    finally:
        conn.close()


def count_under(root: Path) -> int:
    """How many indexed files are inside a folder."""
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM files WHERE path LIKE ?", (str(root) + os.sep + "%",)).fetchone()[0]
    finally:
        conn.close()


def indexed_text(path: str) -> str:
    """What the index knows about a file: AI description for images, metadata/description/transcript for media."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT t.content FROM files f JOIN files_fts t ON t.rowid = f.id WHERE f.path=?", (path,)
        ).fetchone()
        return (row["content"] or "") if row else ""
    finally:
        conn.close()
