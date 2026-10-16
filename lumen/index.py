"""SQLite FTS5 file index: build/refresh it and search it."""

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config
from .extract import extract_text

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
    "caption": "TEXT", "duration": "REAL", "media_done": "INTEGER", "fingerprint": "TEXT",
    # visual search: CLIP signature (512 float32), 64-bit dHash, file hash; visual_done NULL = pending
    "embedding": "BLOB", "dhash": "INTEGER", "sha1": "TEXT", "visual_done": "INTEGER",
}


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
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
    return conn


def _use_wal(conn, attempts: int = 100):
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


def _missing_columns(conn) -> list[str]:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(files)")}
    return [col for col in LATER_COLUMNS if col not in have]


def _drop_derived(conn, file_id: int):
    """Everything derived from a file's contents: transcript lines and document passages."""
    from . import passages

    _drop_segments(conn, file_id)
    passages.drop_file(conn, file_id)


def _drop_segments(conn, file_id: int):
    conn.execute("DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (file_id,))
    conn.execute("DELETE FROM segments WHERE file_id=?", (file_id,))


def delete_file(conn, file_id: int):
    """Drop one file and everything derived from it from the index (the file itself is not touched)."""
    conn.execute("DELETE FROM files WHERE id=?", (file_id,))
    conn.execute("DELETE FROM files_fts WHERE rowid=?", (file_id,))
    _drop_derived(conn, file_id)


def forget(path: str) -> int:
    """Drop a file, or every file under a folder, from the index. Returns how many."""
    path = str(Path(path).expanduser().resolve())
    conn = connect()
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM files WHERE path = ? OR substr(path, 1, ?) = ?", (path, len(path) + 1, path + os.sep))]
        for file_id in ids:
            delete_file(conn, file_id)
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def _walk(root: Path):
    excluded = set(config.EXCLUDED)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden, dependency/build and excluded folders in place
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in config.SKIP_DIRS
                       and os.path.join(dirpath, d) not in excluded]
        for fn in filenames:
            if not fn.startswith(".") and os.path.join(dirpath, fn) not in excluded:
                yield Path(dirpath) / fn


def build_index(roots=None, progress=None, captions=None, on_caption=None, media=None, transcripts=None, on_phase=None) -> dict:
    """Add new/changed files, drop deleted ones, then caption new images/scans
    and describe/transcribe new video and audio.

    Unchanged files are skipped, so re-running only does new work.
    on_phase(name) is called as each pass starts: scan, captions, visual, media, passages.
    """
    from . import power

    phase = on_phase or (lambda name: None)
    power.low_priority()
    roots = roots or config.ROOTS
    conn = connect()
    known = {r["path"]: (r["id"], r["size"], r["mtime"]) for r in conn.execute("SELECT id, path, size, mtime FROM files")}
    seen = set()
    stats = {"scanned": 0, "added": 0, "updated": 0, "removed": 0, "with_text": 0}
    started = time.time()

    phase("scan")
    paused = set(config.PAUSED_ROOTS)
    for root in roots:
        if root in paused or not root.is_dir():
            continue
        for path in _walk(root):
            try:
                st = path.stat()
            except OSError:
                continue
            if not path.is_file():
                continue
            p = str(path)
            seen.add(p)
            stats["scanned"] += 1
            prev = known.get(p)
            if prev and prev[1] == st.st_size and prev[2] == st.st_mtime:
                continue

            ext = path.suffix.lower().lstrip(".")
            text = extract_text(path, ext, st.st_size)
            row = (p, path.name, ext, st.st_size, st.st_mtime, int(bool(text)))
            if prev:
                conn.execute(
                    "UPDATE files SET path=?, name=?, ext=?, size=?, mtime=?, has_text=?, "
                    "caption=NULL, duration=NULL, media_done=NULL, fingerprint=NULL, "
                    "embedding=NULL, dhash=NULL, sha1=NULL, visual_done=NULL WHERE id=?",
                    (*row, prev[0]),
                )
                _drop_derived(conn, prev[0])
                conn.execute("DELETE FROM files_fts WHERE rowid=?", (prev[0],))
                file_id = prev[0]
                stats["updated"] += 1
            else:
                file_id = conn.execute(
                    "INSERT INTO files (path, name, ext, size, mtime, has_text) VALUES (?,?,?,?,?,?)", row
                ).lastrowid
                stats["added"] += 1
            # Split name/path into words so "Ali_Agreement-v2.pdf" matches "agreement"
            conn.execute(
                "INSERT INTO files_fts (rowid, name, path, content) VALUES (?,?,?,?)",
                (file_id, _words(path.stem), _words(str(path.parent)), text),
            )
            if text:
                from . import passages

                passages.index_file(conn, file_id, text)
            stats["with_text"] += bool(text)
            if (stats["added"] + stats["updated"]) % 200 == 0:
                conn.commit()
            if stats["scanned"] % 500 == 0:
                if progress:
                    progress(stats)
                if os.environ.get("LUMEN_PAUSE_FILE"):
                    conn.commit()  # never hold the write lock while paused
                    power.wait_if_paused()

    # Remove files that disappeared from a scanned folder, and files of folders no longer indexed.
    # A configured folder that is missing right now (unplugged drive) or paused keeps its entries.
    walked = tuple(str(r) + os.sep for r in roots if r.is_dir() and r not in paused)
    configured = tuple(str(r) + os.sep for r in roots)
    for p, (file_id, _, _) in known.items():
        if p not in seen and (p.startswith(walked) or not p.startswith(configured)):
            delete_file(conn, file_id)
            stats["removed"] += 1

    conn.commit()
    stats["seconds"] = round(time.time() - started, 1)

    # AI passes (vision model on GPU, whisper on CPU) are the expensive part: skip them on battery
    allowed, why = power.heavy_allowed()
    if not allowed:
        stats["heavy_skipped"] = why
    else:
        from contextlib import nullcontext

        from . import providers

        # Unloading the model after indexing only means something for a local Ollama model
        with power.GpuModel(config.CAPTION_MODEL) if providers.is_ollama("vision") else nullcontext():
            if config.CAPTIONS if captions is None else captions:
                phase("captions")
                from .caption import caption_pending

                try:
                    stats["captions"] = caption_pending(conn, on_caption)
                except ConnectionError as e:
                    stats["captions"] = {"error": f"Vision model ({config.VISION_PROVIDER}) not reachable: {e or 'no connection'}; captions skipped"}

            if config.VISUAL:
                phase("visual")
                from .visual import process_pending as visual_pending

                stats["visual"] = visual_pending(conn, on_caption)

            if config.MEDIA if media is None else media:
                phase("media")
                from .media import process_pending

                try:
                    stats["media"] = process_pending(
                        conn, on_caption, transcripts=config.TRANSCRIPTS if transcripts is None else transcripts
                    )
                except ConnectionError as e:
                    stats["media"] = {"error": f"Vision model ({config.VISION_PROVIDER}) not reachable: {e or 'no connection'}; video/audio skipped"}

    # Passages for anything with new content: documents, and descriptions/transcripts added above
    from . import passages

    phase("passages")
    stats["passages_added"] = passages.backfill(conn)
    conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
    conn.commit()
    conn.close()
    (config.DATA_DIR / "last_index.json").write_text(json.dumps({"at": time.time(), "stats": stats}))
    return stats


def _words(s: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", s))


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
        from .media import fmt_time

        when = datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d")
        length = f"{fmt_time(self.duration)} long, " if self.duration else ""
        out = f"{n}. {self.name}  ({length}{_human(self.size)}, modified {when})\n   path: {self.path}"
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


def kind_of(ext: str) -> str:
    from .caption import IMAGE_EXTS
    from .media import AUDIO_EXTS, VIDEO_EXTS

    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext in ("doc", "docx", "odt", "rtf"):
        return "doc"
    if ext in ("xls", "xlsx", "ods", "csv", "tsv"):
        return "sheet"
    if ext in ("zip", "tar", "gz", "7z", "rar", "xz"):
        return "archive"
    return "file"


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
                    + f" ORDER BY bm25(files_fts, 10.0, 3.0, 1.0) * {_RELEVANCE_SQL} LIMIT ?"
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


DOC_EXTS = (
    "pdf doc docx odt rtf txt xls xlsx ods csv tsv ppt pptx odp epub "
    "jpg jpeg png webp gif bmp tif tiff heic mp4 mkv mov webm avi m4v 3gp wmv mp3 m4a wav ogg opus flac aac"
).split()
MIXED_EXTS = "md html htm zip rar 7z tar gz".split()  # sometimes personal, often project files

# Multiplier on the (negative) bm25 score: 1 keeps documents on top, smaller values push files down
_RELEVANCE_SQL = (
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
            "files": total, "with_text": with_text, "captioned": captioned,
            "media_indexed": media, "transcript_lines": segments, "visual_indexed": visual,
            "db": str(config.DB_PATH),
        }
    finally:
        conn.close()


def _ts(date: str) -> float:
    return datetime.strptime(date.strip()[:10], "%Y-%m-%d").timestamp()


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


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
