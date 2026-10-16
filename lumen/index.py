"""SQLite FTS5 file index: build/refresh it and search it."""

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .extract import extract_text
from .core import limits
from .core.settings import settings
from .storage.catalog import delete_file, drop_derived
from .storage.db import connect


def _walk(root: Path):
    excluded = set(settings.excluded)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden, dependency/build and excluded folders in place
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in limits.SKIP_DIRS
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
    roots = roots or settings.roots
    conn = connect()
    known = {r["path"]: (r["id"], r["size"], r["mtime"]) for r in conn.execute("SELECT id, path, size, mtime FROM files")}
    seen = set()
    stats = {"scanned": 0, "added": 0, "updated": 0, "removed": 0, "with_text": 0}
    started = time.time()

    phase("scan")
    paused = set(settings.paused_roots)
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
                drop_derived(conn, prev[0])
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
        with power.GpuModel(settings.caption_model) if providers.is_ollama("vision") else nullcontext():
            if settings.captions if captions is None else captions:
                phase("captions")
                from .caption import caption_pending

                try:
                    stats["captions"] = caption_pending(conn, on_caption)
                except ConnectionError as e:
                    stats["captions"] = {"error": f"Vision model ({settings.vision_provider}) not reachable: {e or 'no connection'}; captions skipped"}

            if settings.visual:
                phase("visual")
                from .visual import process_pending as visual_pending

                stats["visual"] = visual_pending(conn, on_caption)

            if settings.media if media is None else media:
                phase("media")
                from .media import process_pending

                try:
                    stats["media"] = process_pending(
                        conn, on_caption, transcripts=settings.transcripts if transcripts is None else transcripts
                    )
                except ConnectionError as e:
                    stats["media"] = {"error": f"Vision model ({settings.vision_provider}) not reachable: {e or 'no connection'}; video/audio skipped"}

    # Passages for anything with new content: documents, and descriptions/transcripts added above
    from . import passages

    phase("passages")
    stats["passages_added"] = passages.backfill(conn)
    conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
    conn.commit()
    conn.close()
    (settings.data_dir / "last_index.json").write_text(json.dumps({"at": time.time(), "stats": stats}))
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


def _ts(date: str) -> float:
    return datetime.strptime(date.strip()[:10], "%Y-%m-%d").timestamp()


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
