"""Full-text search over file names, folders, document text, image and video descriptions and
what is said in videos: phrase first, then all words, then any word."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..core.filetypes import DOC_EXTS, MIXED_EXTS, kind_of
from ..core.formatting import fmt_time, human_size
from ..storage.db import connect
from .query import match_exprs, query_terms


@dataclass
class Hit:
    path: str
    name: str
    ext: str
    size: int
    mtime: float
    snippet: str = ""
    duration: float | None = None
    at: float | None = None  # where in a video/audio the words are said
    at_text: str = ""
    partial: bool = False  # found by the "any word" fallback: not every word matched

    def line(self, n: int) -> str:
        when = datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d")
        length = f"{fmt_time(self.duration)} long, " if self.duration else ""
        out = f"{n}. {self.name}  ({length}{human_size(self.size)}, modified {when})\n   path: {self.path}"
        if self.partial:
            out += "\n   (partial match: not all words found)"
        if self.at is not None:
            # exactly the argument open_file needs, so a small model copies it instead of converting mm:ss
            out += f'\n   said at start_seconds={int(self.at)} ({fmt_time(self.at)}): "{self.at_text}"'
        elif self.snippet:
            out += f"\n   match: {self.snippet}"
        return out

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "ext": self.ext,
            "size": self.size,
            "mtime": self.mtime,
            "snippet": self.snippet,
            "duration": self.duration,
            "at": self.at,
            "at_text": self.at_text,
            "kind": kind_of(self.ext),
            "partial": self.partial,
        }


def search(
    query: str = "",
    ext: str = "",
    modified_after: str = "",
    modified_before: str = "",
    folder: str = "",
    limit: int = 10,
    min_minutes: float = 0,
    max_minutes: float = 0,
) -> list[Hit]:
    """Full-text search over file names, paths and contents, with optional filters."""
    conn = connect()
    where, params = [], []

    exts = [e.strip().lower().lstrip(".") for e in re.split(r"[,\s]+", ext) if e.strip()]
    if exts:
        where.append(f"f.ext IN ({','.join('?' * len(exts))})")
        params += exts
    if modified_after:
        where.append("f.mtime >= ?")
        params.append(_ts(modified_after))
    if modified_before:
        # inclusive: the whole "before" day counts
        where.append("f.mtime < ?")
        params.append(_ts(modified_before) + 86400)
    if folder:
        where.append("f.path LIKE ?")
        params.append(f"%{folder}%")
    if min_minutes:
        where.append("f.duration >= ?")
        params.append(min_minutes * 60)
    if max_minutes:
        where.append("f.duration <= ?")
        params.append(max_minutes * 60)

    terms = query_terms(query)
    try:
        if not terms:
            # Filter-only request, e.g. "PDFs from last week": newest first
            sql = "SELECT f.* , '' AS snip FROM files f"
            sql += (" WHERE " + " AND ".join(where)) if where else ""
            sql += " ORDER BY f.mtime DESC LIMIT ?"
            rows = conn.execute(sql, (*params, limit)).fetchall()
        else:
            rows = []
            # Exact phrase first, then "all words", then "any word"
            partial = False
            for match, is_partial in match_exprs(terms):
                sql = (
                    "SELECT f.*, snippet(files_fts, 2, '[', ']', '…', 12) AS snip "
                    "FROM files_fts JOIN files f ON f.id = files_fts.rowid "
                    "WHERE files_fts MATCH ?"
                    + "".join(" AND " + w for w in where)
                    # name hits weigh most, then folder names, then content; personal documents
                    # beat code/assets of projects that merely mention the same word (bm25: lower = better)
                    + f" ORDER BY bm25(files_fts, 10.0, 3.0, 1.0) * {RELEVANCE_SQL} LIMIT ?"
                )
                rows = conn.execute(sql, (match, *params, limit)).fetchall()
                if rows:
                    partial = is_partial
                    break
        hits = [
            Hit(
                r["path"],
                r["name"],
                r["ext"],
                r["size"],
                r["mtime"],
                " ".join((r["snip"] or "").split()),
                r["duration"],
                partial=bool(terms) and partial,
            )
            for r in rows
        ]
        if terms:
            for hit, r in zip(hits, rows, strict=True):
                if r["media_done"] == 1:
                    _locate(conn, hit, r["id"], terms)
    finally:
        conn.close()
    return hits


# Multiplier on the (negative) bm25 score: 1 keeps documents on top, smaller values push files down
RELEVANCE_SQL = (
    "(CASE WHEN f.ext IN (" + ",".join(f"'{e}'" for e in DOC_EXTS) + ") THEN 1.0 "
    "WHEN f.ext IN (" + ",".join(f"'{e}'" for e in MIXED_EXTS) + ") THEN 0.6 ELSE 0.3 END)"
)


def _locate(conn: sqlite3.Connection, hit: Hit, file_id: int, terms: list[str]) -> None:
    """Find the transcript line that best matches, so the agent can open the video right there."""
    # Strict steps only: a loose match would point at a random line containing one common word
    for match, _ in match_exprs(terms, loose=False):
        row = conn.execute(
            "SELECT s.start, s.text FROM segments_fts JOIN segments s ON s.id = segments_fts.rowid "
            "WHERE segments_fts MATCH ? AND s.file_id = ? ORDER BY bm25(segments_fts) LIMIT 1",
            (match, file_id),
        ).fetchone()
        if row:
            hit.at, hit.at_text = row["start"], row["text"][:160]
            return


def _ts(date: str) -> float:
    return datetime.strptime(date.strip()[:10], "%Y-%m-%d").timestamp()
