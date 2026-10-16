"""Describe images and scanned PDFs with a local vision model so they become searchable."""

import logging
import sqlite3
import time

import pymupdf

from ...core import limits
from ...core.filetypes import IMAGE_EXTS
from ...providers import backends
from .. import power
from ..progress import ItemReport

log = logging.getLogger(__name__)

MIN_IMAGE_BYTES = 10 * 1024  # smaller images are usually icons/UI assets: not worth a caption
MAX_SIDE = 768  # downscale before sending: faster and enough detail

PROMPT = (
    "Describe this {kind} in 1-2 sentences for a file search index: what it is "
    "(e.g. ID card, receipt, invoice, screenshot, photo of ...) and the main subject. "
    "Then on a new line starting with 'Text:' copy the important visible text "
    "(names, numbers, dates, titles), or write 'Text: none'."
)


def wants_caption(ext: str, size: int, has_text: bool) -> bool:
    if ext in IMAGE_EXTS:
        return MIN_IMAGE_BYTES <= size <= limits.MAX_RENDER_BYTES
    # PDFs with no text layer are almost always scans
    return ext == "pdf" and not has_text and size <= limits.MAX_RENDER_BYTES


def _render(path: str) -> bytes:
    """First page/frame of the file as a downscaled PNG."""
    try:
        with pymupdf.open(path) as doc:
            page = doc[0]
            zoom = min(1.0 if not doc.is_pdf else 2.0, MAX_SIDE / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    except Exception as e:
        if path.lower().endswith(".pdf"):
            raise
        log.debug("PyMuPDF can't open %s (%s); trying PIL", path, e)
    # Formats PyMuPDF can't open (e.g. webp)
    from io import BytesIO

    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def caption_pending(conn: sqlite3.Connection, progress: ItemReport | None = None) -> dict:
    """Caption every image/scan that has no caption yet. Returns stats.

    caption IS NULL means "not done yet"; "" means "skipped or failed" so it isn't retried
    until the file changes.
    """
    rows = conn.execute("SELECT id, path, ext, size, has_text FROM files WHERE caption IS NULL").fetchall()
    todo = [r for r in rows if wants_caption(r["ext"], r["size"], bool(r["has_text"]))]
    todo_ids = {r["id"] for r in todo}
    skip = [r["id"] for r in rows if r["id"] not in todo_ids]
    conn.executemany("UPDATE files SET caption='' WHERE id=?", [(i,) for i in skip])
    conn.commit()

    stats = {"captioned": 0, "failed": 0, "seconds": 0.0}
    if not todo:
        return stats

    started = time.time()
    for n, r in enumerate(todo, 1):
        allowed, why = power.heavy_allowed()
        if not allowed:
            stats["stopped"] = f"stopped: {why}; {len(todo) - n + 1} left for next run"
            break
        power.wait_until_idle()
        kind = "scanned document page" if r["ext"] == "pdf" else "image"
        try:
            caption = backends.describe_image(PROMPT.format(kind=kind), _render(r["path"]))
            stats["captioned"] += 1
        except ConnectionError:
            raise  # Ollama isn't running: stop, and leave the rest for the next run
        except Exception as e:
            log.warning("caption failed for %s: %s", r["path"], e)
            caption = ""
            stats["failed"] += 1
            if progress:
                progress(n, len(todo), r["path"], f"failed: {e}")
        conn.execute("UPDATE files SET caption=? WHERE id=?", (caption, r["id"]))
        if caption:
            conn.execute("UPDATE files_fts SET content=? WHERE rowid=?", (caption, r["id"]))
            if progress:
                progress(n, len(todo), r["path"], caption)
        conn.commit()

    stats["seconds"] = round(time.time() - started, 1)
    return stats
