"""SQLite FTS5 file index: build/refresh it and search it."""

import json
import os
import re
import time
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
                from .search import passages

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
                from .search.images import process_pending as visual_pending

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
    from .search import passages

    phase("passages")
    stats["passages_added"] = passages.backfill(conn)
    conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
    conn.commit()
    conn.close()
    (settings.data_dir / "last_index.json").write_text(json.dumps({"at": time.time(), "stats": stats}))
    return stats


def _words(s: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", s))
