"""Preview images for the app: a frame of a video, the first page of a PDF, a scaled image."""

import logging
import subprocess
from io import BytesIO
from pathlib import Path

from ..core.filetypes import kind_of

log = logging.getLogger(__name__)


def render(p: Path, w: int, t: float | None) -> bytes | None:
    ext = p.suffix.lower().lstrip(".")
    kind = kind_of(ext)
    try:
        if kind == "video":
            from ..indexing.passes.media import probe

            at = t if t is not None else max(1.0, probe(str(p))["duration"] * 0.15)
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-threads", "1", "-ss", f"{at:.2f}", "-i", str(p), "-frames:v", "1",
                 "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                capture_output=True, timeout=60,
            ).stdout
            return out or None
        if kind in ("pdf", "image"):
            import pymupdf

            try:
                with pymupdf.open(p) as doc:
                    page = doc[0]
                    zoom = w / page.rect.width
                    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
            except Exception as e:
                log.debug("no PDF thumbnail for %s: %s", p, e)
                if kind == "pdf":
                    return None
            from PIL import Image

            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((w, w * 2))
                buf = BytesIO()
                im.save(buf, "PNG")
                return buf.getvalue()
    except Exception as e:  # unreadable or unsupported image: the app shows the file icon
        log.debug("no thumbnail for %s: %s", p, e)
        return None
    return None
