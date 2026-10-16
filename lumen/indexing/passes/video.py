"""What a video or audio file is: its metadata (ffprobe), and what it shows (frames sampled across
it, described by the vision model)."""

import json
import logging
import os
import subprocess
from io import BytesIO

from ...core.filetypes import VIDEO_EXTS
from ...core.formatting import fmt_time

log = logging.getLogger(__name__)


FRAMES = 6  # frames sampled across the video, shown to the model as one 3x2 grid
FRAME_WIDTH = 320

PROMPT = (
    'These are {n} frames taken in order from one video ({length}, file name "{name}"). Describe the video '
    "in 1-2 sentences for a file search index: what kind of video it is (e.g. TV episode, phone recording, "
    "screen recording, drone shot) and what happens or is shown. Do NOT guess the names of films, shows or "
    "people; only use names written on screen or in the file name. Then on a new line starting with 'Text:' "
    "copy important on-screen text, or write 'Text: none'."
)


# ---------- layer 1: metadata ----------


def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    data = json.loads(out.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1),
        None,
    )
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
            [
                "ffmpeg",
                "-v",
                "error",
                "-threads",
                "1",
                "-ss",
                f"{t:.2f}",
                "-i",
                path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={FRAME_WIDTH}:-2",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            timeout=120,
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
    from ...providers import backends

    grid, n = frame_grid(path, duration)
    name = os.path.basename(path)
    return backends.describe_image(PROMPT.format(n=n, length=fmt_time(duration), name=name), grid)
