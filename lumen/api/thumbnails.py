"""Pictures for the app: a frame of a video, a page of a PDF, a scaled image (thumbnails, and
the viewer's pages and full-size images), kept in a disk cache."""

import hashlib
import logging
import subprocess
from io import BytesIO
from pathlib import Path

from ..core.filetypes import kind_of
from ..core.settings import settings

log = logging.getLogger(__name__)


def cached(p: Path, w: int, t: float | None = None, page: int = 0, upscale: bool = True) -> bytes | None:
    """render(), from the disk cache when this file (as it is now) was drawn at this size before."""
    st = p.stat()
    key = hashlib.sha1(f"{p}|{st.st_mtime}|{w}|{t}|{page}|{upscale}".encode()).hexdigest()
    cache = settings.data_dir / "thumbs" / f"{key}.png"
    if cache.exists():
        return cache.read_bytes()
    png = render(p, w, t, page, upscale)
    if png is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(png)
    return png


def render(p: Path, w: int, t: float | None, page: int = 0, upscale: bool = True) -> bytes | None:
    ext = p.suffix.lower().lstrip(".")
    kind = kind_of(ext)
    try:
        if kind == "video":
            from ..indexing.passes.video import probe

            at = t if t is not None else max(1.0, probe(str(p))["duration"] * 0.15)
            out = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-threads",
                    "1",
                    "-ss",
                    f"{at:.2f}",
                    "-i",
                    str(p),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={w}:-2",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "-",
                ],
                capture_output=True,
                timeout=60,
            ).stdout
            return out or None
        if kind == "pdf" or (kind == "image" and upscale):
            import pymupdf

            try:
                with pymupdf.open(p) as doc:
                    pg = doc[max(0, min(page, doc.page_count - 1))]
                    zoom = w / pg.rect.width
                    return pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
            except Exception as e:
                log.debug("no PDF thumbnail for %s: %s", p, e)
                if kind == "pdf":
                    return None
        if kind == "image":  # a full-size image, or one pymupdf can't read: PIL (keeps pixel sizes)
            from PIL import Image

            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((w, w * 2))  # only ever shrinks
                buf = BytesIO()
                im.save(buf, "PNG")
                return buf.getvalue()
    except Exception as e:  # unreadable or unsupported image: the app shows the file icon
        log.debug("no thumbnail for %s: %s", p, e)
        return None
    return None
