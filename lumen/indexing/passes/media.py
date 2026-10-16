"""Make video/audio searchable (one index pass): metadata and what it shows (video.py), what is
said (speech.py), and the work shared between identical copies of the same file."""

import hashlib
import logging
import os
import sqlite3
import time

from ...core import limits
from ...core.filetypes import MEDIA_EXTS
from ...core.settings import settings
from .. import power
from ..progress import ItemReport
from . import speech, video

log = logging.getLogger(__name__)


# ---------- the indexing pass ----------


def _fingerprint(path: str, size: int) -> str:
    """Cheap content id (size + first/last MB) so identical copies are only processed once."""
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()


def process_pending(conn: sqlite3.Connection, progress: ItemReport | None = None, transcripts: bool = True) -> dict:
    """Index every video/audio file that hasn't been processed (media_done IS NULL)."""
    rows = conn.execute(
        f"SELECT id, path, ext, size FROM files WHERE media_done IS NULL "
        f"AND ext IN ({','.join('?' * len(MEDIA_EXTS))})",
        sorted(MEDIA_EXTS),
    ).fetchall()
    stats = {"media": 0, "described": 0, "transcribed": 0, "reused": 0, "failed": 0, "seconds": 0.0}
    if rows and transcripts:
        try:
            speech.load_whisper()
        except Exception as e:
            log.exception("speech model %s could not be loaded", settings.whisper_model)
            # Leave everything pending (not failed) so the next run retries with transcripts
            model = settings.whisper_model
            return {"error": f"speech model '{model}' could not be loaded ({e}); video/audio left for next run"}
    started = time.time()
    done_by_fp: dict[str, int] = {}

    for n, r in enumerate(rows, 1):
        path, ext = r["path"], r["ext"]

        def say(msg: str, n: int = n, path: str = path) -> None:
            if progress:
                progress(n, len(rows), path, msg)

        allowed, why = power.heavy_allowed()
        if not allowed:
            stats["stopped"] = f"stopped: {why}; {len(rows) - n + 1} left for next run"
            break
        power.wait_until_idle()
        try:
            fp = _fingerprint(path, r["size"])
            twin = done_by_fp.get(fp) or _find_twin(conn, fp, r["id"])
            if twin:
                _copy_media(conn, twin, r["id"], fp)
                stats["reused"] += 1
                say("identical to an already indexed file: reused its description and transcript")
                conn.commit()
                continue

            meta = video.probe(path)
            parts = [video.describe_meta(meta, ext)]
            say(parts[0])

            caption = ""
            if meta["has_video"] and meta["duration"] > 0:
                caption = video.describe_frames(path, meta["duration"])
                parts.append("Shows: " + caption)
                stats["described"] += 1
                say(caption)

            conn.execute(
                "DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (r["id"],)
            )
            conn.execute("DELETE FROM segments WHERE file_id=?", (r["id"],))
            if transcripts and meta["has_audio"]:
                t0 = time.time()
                segs, lang = speech.transcribe(path)
                for start, end, text in segs:
                    sid = conn.execute(
                        "INSERT INTO segments (file_id, start, end, text) VALUES (?,?,?,?)", (r["id"], start, end, text)
                    ).lastrowid
                    conn.execute("INSERT INTO segments_fts (rowid, text) VALUES (?,?)", (sid, text))
                if segs:
                    parts.append(f"Transcript ({lang}): " + " ".join(s[2] for s in segs))
                    stats["transcribed"] += 1
                say(f"transcribed {len(segs)} segments ({lang}) in {time.time() - t0:.0f}s")

            content = "\n".join(parts)[: limits.MAX_CONTENT_CHARS]
            conn.execute(
                "UPDATE files SET duration=?, caption=?, media_done=1, fingerprint=? WHERE id=?",
                (meta["duration"], caption, fp, r["id"]),
            )
            conn.execute("UPDATE files_fts SET content=? WHERE rowid=?", (content, r["id"]))
            done_by_fp[fp] = r["id"]
            stats["media"] += 1
        except ConnectionError:
            raise
        except Exception as e:
            log.warning("video/audio failed for %s: %s", r["path"], e)
            stats["failed"] += 1
            conn.execute("UPDATE files SET media_done=0 WHERE id=?", (r["id"],))
            say(f"failed: {e}")
        conn.commit()

    stats["seconds"] = round(time.time() - started, 1)
    return stats


def _find_twin(conn: sqlite3.Connection, fp: str, file_id: int) -> int | None:
    row = conn.execute("SELECT id FROM files WHERE fingerprint=? AND media_done=1 AND id<>?", (fp, file_id)).fetchone()
    return row["id"] if row else None


def _copy_media(conn: sqlite3.Connection, src: int, dst: int, fp: str) -> None:
    duration, caption = conn.execute("SELECT duration, caption FROM files WHERE id=?", (src,)).fetchone()
    content = conn.execute("SELECT content FROM files_fts WHERE rowid=?", (src,)).fetchone()[0]
    conn.execute(
        "UPDATE files SET duration=?, caption=?, media_done=1, fingerprint=? WHERE id=?", (duration, caption, fp, dst)
    )
    conn.execute("UPDATE files_fts SET content=? WHERE rowid=?", (content, dst))
    conn.execute("DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (dst,))
    conn.execute("DELETE FROM segments WHERE file_id=?", (dst,))
    for start, end, text in conn.execute("SELECT start, end, text FROM segments WHERE file_id=?", (src,)).fetchall():
        sid = conn.execute(
            "INSERT INTO segments (file_id, start, end, text) VALUES (?,?,?,?)", (dst, start, end, text)
        ).lastrowid
        conn.execute("INSERT INTO segments_fts (rowid, text) VALUES (?,?)", (sid, text))
