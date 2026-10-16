"""Make video/audio searchable: metadata (ffprobe), what it shows (frames -> vision model)
and what is said (faster-whisper transcript with timestamps)."""

import hashlib
import json
import os
import subprocess
import time
from io import BytesIO

from ...core import limits
from ...core.filetypes import MEDIA_EXTS, VIDEO_EXTS
from ...core.formatting import fmt_time
from ...core.settings import settings
from .. import power


FRAMES = 6         # frames sampled across the video, shown to the model as one 3x2 grid
FRAME_WIDTH = 320

PROMPT = (
    "These are {n} frames taken in order from one video ({length}, file name \"{name}\"). Describe the video "
    "in 1-2 sentences for a file search index: what kind of video it is (e.g. TV episode, phone recording, "
    "screen recording, drone shot) and what happens or is shown. Do NOT guess the names of films, shows or "
    "people; only use names written on screen or in the file name. Then on a new line starting with 'Text:' "
    "copy important on-screen text, or write 'Text: none'."
)


# ---------- layer 1: metadata ----------

def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(out.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    return {
        "duration": float(fmt.get("duration") or 0),
        "width": video and video.get("width"),
        "height": video and video.get("height"),
        "has_video": video is not None,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "created": (tags.get("creation_time") or "")[:10],
        "title": tags.get("title", ""),
    }


def describe_meta(m: dict, ext: str) -> str:
    kind = "Video" if m["has_video"] and ext in VIDEO_EXTS else "Audio"
    parts = [f"{kind}, {fmt_time(m['duration'])} long"]
    if m["width"]:
        parts.append(f"{m['width']}x{m['height']}" + (" 4K" if max(m["width"], m["height"]) >= 3840 else ""))
    if m["created"]:
        parts.append(f"recorded {m['created']}")
    if m["title"]:
        parts.append(f"title {m['title']}")
    if m["has_video"] and not m["has_audio"]:
        parts.append("no sound")
    return ", ".join(parts) + "."


# ---------- layer 2: what it shows ----------

def frame_grid(path: str, duration: float) -> tuple[bytes, int]:
    from PIL import Image

    frames = []
    for i in range(FRAMES):
        t = duration * (i + 0.5) / FRAMES
        png = subprocess.run(
            ["ffmpeg", "-v", "error", "-threads", "1", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
             "-vf", f"scale={FRAME_WIDTH}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True, timeout=120,
        ).stdout
        if png:
            frames.append(Image.open(BytesIO(png)).convert("RGB"))
    if not frames:
        raise RuntimeError("could not extract frames")
    w, h = frames[0].size
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    grid = Image.new("RGB", (w * cols, h * rows), "black")
    for i, f in enumerate(frames):
        grid.paste(f.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    buf = BytesIO()
    grid.save(buf, "PNG")
    return buf.getvalue(), len(frames)


def describe_frames(path: str, duration: float) -> str:
    from ... import providers

    grid, n = frame_grid(path, duration)
    name = os.path.basename(path)
    return providers.describe_image(PROMPT.format(n=n, length=fmt_time(duration), name=name), grid)


# ---------- layer 3: what is said ----------

_whisper = None


def load_whisper():
    """Load (downloading on first use) the speech model. Runs on CPU so the GPU stays free for the LLM."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        _whisper = WhisperModel(
            settings.whisper_model, device="cpu", compute_type="int8",
            cpu_threads=power.threads(),
            download_root=str(settings.data_dir / "models"),
        )
    return _whisper


def transcribe(path: str) -> tuple[list[tuple[float, float, str]], str]:
    """Return ([(start, end, text), ...], language)."""
    import numpy as np

    # Decode with ffmpeg ourselves (16 kHz mono float32): faster-whisper's own PyAV decoding
    # breaks with PyAV >= 19, and ffmpeg handles more containers anyway.
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-threads", str(power.threads()), "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, timeout=3600,
    ).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    if audio.size == 0:
        return [], ""
    # temperature=0 only: no slow re-decoding passes on hard audio (saves CPU/battery)
    segments, info = load_whisper().transcribe(
        audio, vad_filter=True, beam_size=1, condition_on_previous_text=False, temperature=0.0
    )
    if info.language_probability < 0.6:
        return [], ""  # noise/music, not speech: whisper only produces junk here
    return [
        (s.start, s.end, s.text.strip())
        for s in segments
        if s.text.strip() and s.no_speech_prob < 0.8 and any(ch.isalnum() for ch in s.text)
    ], info.language


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


def process_pending(conn, progress=None, transcripts=True) -> dict:
    """Index every video/audio file that hasn't been processed (media_done IS NULL)."""
    rows = conn.execute(
        f"SELECT id, path, ext, size FROM files WHERE media_done IS NULL "
        f"AND ext IN ({','.join('?' * len(MEDIA_EXTS))})",
        sorted(MEDIA_EXTS),
    ).fetchall()
    stats = {"media": 0, "described": 0, "transcribed": 0, "reused": 0, "failed": 0, "seconds": 0.0}
    if rows and transcripts:
        try:
            load_whisper()
        except Exception as e:
            # Leave everything pending (not failed) so the next run retries with transcripts
            return {"error": f"speech model '{settings.whisper_model}' could not be loaded ({e}); video/audio left for next run"}
    started = time.time()
    done_by_fp: dict[str, int] = {}

    for n, r in enumerate(rows, 1):
        path, ext = r["path"], r["ext"]
        say = (lambda msg: progress(n, len(rows), path, msg)) if progress else (lambda msg: None)
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

            meta = probe(path)
            parts = [describe_meta(meta, ext)]
            say(parts[0])

            caption = ""
            if meta["has_video"] and meta["duration"] > 0:
                caption = describe_frames(path, meta["duration"])
                parts.append("Shows: " + caption)
                stats["described"] += 1
                say(caption)

            conn.execute("DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (r["id"],))
            conn.execute("DELETE FROM segments WHERE file_id=?", (r["id"],))
            if transcripts and meta["has_audio"]:
                t0 = time.time()
                segs, lang = transcribe(path)
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
            stats["failed"] += 1
            conn.execute("UPDATE files SET media_done=0 WHERE id=?", (r["id"],))
            say(f"failed: {e}")
        conn.commit()

    stats["seconds"] = round(time.time() - started, 1)
    return stats


def _find_twin(conn, fp: str, file_id: int):
    row = conn.execute("SELECT id FROM files WHERE fingerprint=? AND media_done=1 AND id<>?", (fp, file_id)).fetchone()
    return row["id"] if row else None


def _copy_media(conn, src: int, dst: int, fp: str):
    duration, caption = conn.execute("SELECT duration, caption FROM files WHERE id=?", (src,)).fetchone()
    content = conn.execute("SELECT content FROM files_fts WHERE rowid=?", (src,)).fetchone()[0]
    conn.execute("UPDATE files SET duration=?, caption=?, media_done=1, fingerprint=? WHERE id=?", (duration, caption, fp, dst))
    conn.execute("UPDATE files_fts SET content=? WHERE rowid=?", (content, dst))
    conn.execute("DELETE FROM segments_fts WHERE rowid IN (SELECT id FROM segments WHERE file_id=?)", (dst,))
    conn.execute("DELETE FROM segments WHERE file_id=?", (dst,))
    for start, end, text in conn.execute("SELECT start, end, text FROM segments WHERE file_id=?", (src,)).fetchall():
        sid = conn.execute("INSERT INTO segments (file_id, start, end, text) VALUES (?,?,?,?)", (dst, start, end, text)).lastrowid
        conn.execute("INSERT INTO segments_fts (rowid, text) VALUES (?,?)", (sid, text))
