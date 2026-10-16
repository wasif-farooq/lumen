"""Full-text search over file names, folders, document text, image and video descriptions and
what is said in videos: phrase first, then all words, then any word."""

import re
from dataclasses import dataclass
from datetime import datetime

from ..core.filetypes import DOC_EXTS, MIXED_EXTS, kind_of
from ..core.formatting import fmt_time, human_size
from ..storage.db import connect


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
            "path": self.path, "name": self.name, "ext": self.ext, "size": self.size, "mtime": self.mtime,
            "snippet": self.snippet, "duration": self.duration, "at": self.at, "at_text": self.at_text,
            "kind": kind_of(self.ext), "partial": self.partial,
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
            for match, partial in _match_exprs(terms):
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
                    break
        hits = [
            Hit(r["path"], r["name"], r["ext"], r["size"], r["mtime"], " ".join((r["snip"] or "").split()), r["duration"],
                partial=bool(terms) and partial)
            for r in rows
        ]
        if terms:
            for hit, r in zip(hits, rows):
                if r["media_done"] == 1:
                    _locate(conn, hit, r["id"], terms)
    finally:
        conn.close()
    return hits


STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by", "from", "is", "are", "was",
    "be", "it", "its", "this", "that", "what", "which", "who", "where", "when", "how", "does", "do", "did", "i",
    "me", "my", "you", "your", "we", "our", "he", "she", "they", "them", "someone", "says", "say", "said", "s",
    # request words: "find my CV" is a search for "cv"
    "find", "show", "open", "search", "look", "get", "give", "list", "please", "can", "could", "file", "files",
    "all", "any", "some", "have", "got", "about", "there", "here", "pls",
}


# Multiplier on the (negative) bm25 score: 1 keeps documents on top, smaller values push files down
RELEVANCE_SQL = (
    "(CASE WHEN f.ext IN (" + ",".join(f"'{e}'" for e in DOC_EXTS) + ") THEN 1.0 "
    "WHEN f.ext IN (" + ",".join(f"'{e}'" for e in MIXED_EXTS) + ") THEN 0.6 ELSE 0.3 END)"
)


def _term(t: str) -> str:
    """FTS5 term: prefix match for real words ("invoic" finds "invoices"), exact match for short
    ones, which would otherwise hit unrelated longer words ("cv" in "cva", "tax" stays prefix)."""
    return f'"{t}"' if len(t) <= 2 or (len(t) == 3 and not t.isalpha()) or t in _EXACT_SHORT else f'"{t}"*'


# 3-letter words that are usually abbreviations, where a prefix match is noise
_EXACT_SHORT = {"cv", "id", "pdf", "cnic", "ntn", "pay", "car", "bill"}


def query_terms(query: str) -> list[str]:
    """Search words, with TV episode notation unified to how files are named:
    "season 1 episode 2", "s1e2", "1x02" -> "s01e02"."""
    q = query.lower()
    ep = lambda m: f" s{int(m.group(1)):02d}e{int(m.group(2)):02d} "
    q = re.sub(r"\bseason\s*(\d{1,2})[\s,]*(?:episode|ep|e)\s*(\d{1,3})\b", ep, q)
    q = re.sub(r"\bs(\d{1,2})\s*e(\d{1,3})\b", ep, q)
    q = re.sub(r"\b(\d{1,2})x(\d{2,3})\b", ep, q)
    return re.findall(r"[^\W_]+", q)


def _match_exprs(terms: list[str], loose: bool = True) -> list[tuple[str, bool]]:
    """FTS5 queries from strictest to loosest: exact phrase, all words, any word.
    Each comes with a flag: True when it is the partial ("any word") step.
    The looser steps skip filler words, bare numbers and very short words,
    which would otherwise match nearly everything (dates, resolutions, "it", "1")."""
    if len(terms) == 1:
        return [(_term(terms[0]), False)]
    content = [t for t in terms if t not in STOPWORDS] or terms
    exprs = [('"' + " ".join(terms) + '"', False), (" AND ".join(_term(t) for t in content), False)]
    meaningful = [t for t in content if len(t) >= 3 and not t.isdigit()]
    if loose and len(meaningful) > 1:
        exprs.append((" OR ".join(_term(t) for t in meaningful), True))
    return exprs


def _locate(conn, hit: Hit, file_id: int, terms: list[str]):
    """Find the transcript line that best matches, so the agent can open the video right there."""
    # Strict steps only: a loose match would point at a random line containing one common word
    for match, _ in _match_exprs(terms, loose=False):
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
