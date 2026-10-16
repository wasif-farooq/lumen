"""The first pass: walk the indexed folders, add new and changed files with their text, and drop
files that are gone. Unchanged files (same size and time) are skipped."""

import os
import re
import time
from pathlib import Path

from ..core import limits
from ..core.settings import settings
from ..search import passages
from ..storage.catalog import delete_file, drop_derived
from . import power
from .extract import extract_text
from .progress import Progress


def walk(root: Path):
    """Files under a folder, skipping hidden files, dependency/build folders and excluded paths."""
    excluded = set(settings.excluded)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden, dependency/build and excluded folders in place
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in limits.SKIP_DIRS
                       and os.path.join(dirpath, d) not in excluded]
        for fn in filenames:
            if not fn.startswith(".") and os.path.join(dirpath, fn) not in excluded:
                yield Path(dirpath) / fn


def words(s: str) -> str:
    """Split names into words so "Ali_Agreement-v2.pdf" matches "agreement"."""
    return " ".join(re.findall(r"[^\W_]+", s))


def scan(conn, roots: list[Path], progress: Progress) -> dict:
    known = {r["path"]: (r["id"], r["size"], r["mtime"]) for r in conn.execute("SELECT id, path, size, mtime FROM files")}
    seen = set()
    stats = {"scanned": 0, "added": 0, "updated": 0, "removed": 0, "with_text": 0}
    started = time.time()
    paused = set(settings.paused_roots)
    for root in roots:
        if root in paused or not root.is_dir():
            continue
        for path in walk(root):
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
            if not (prev and prev[1] == st.st_size and prev[2] == st.st_mtime):
                _add_or_update(conn, path, st, prev, stats)
            if stats["scanned"] % 500 == 0:
                progress.scanned(stats["scanned"])
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
    return stats


def _add_or_update(conn, path: Path, st, prev, stats: dict):
    ext = path.suffix.lower().lstrip(".")
    text = extract_text(path, ext, st.st_size)
    row = (str(path), path.name, ext, st.st_size, st.st_mtime, int(bool(text)))
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
    conn.execute(
        "INSERT INTO files_fts (rowid, name, path, content) VALUES (?,?,?,?)",
        (file_id, words(path.stem), words(str(path.parent)), text),
    )
    if text:
        passages.index_file(conn, file_id, text)
    stats["with_text"] += bool(text)
    if (stats["added"] + stats["updated"]) % 200 == 0:
        conn.commit()
