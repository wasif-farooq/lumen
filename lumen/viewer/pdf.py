"""PDFs for the viewer: how many pages, a page's text, and where words are on the pages (pymupdf).
Pages are drawn by thumbnails.render (same renderer and cache as the thumbnails)."""

from pathlib import Path

from ..core import errors

MAX_MATCHES = 200  # rectangles returned for one search


def page_count(p: Path) -> int:
    import pymupdf

    with pymupdf.open(p) as doc:
        return doc.page_count


def page_text(p: Path, page: int) -> str:
    import pymupdf

    with pymupdf.open(p) as doc:
        if not 0 <= page < doc.page_count:
            raise errors.NotFound(f"No page {page + 1} (this PDF has {doc.page_count}).")
        return str(doc[page].get_text())


def find(p: Path, query: str) -> list[dict]:
    """Where the words are: [{page, rects: [[x0, y0, x1, y1], ...]}] with each rectangle as a
    fraction of the page (0-1), so the app can draw it at any zoom. A phrase that isn't found as a
    whole is looked for word by word (a search hit's snippet is several words)."""
    import pymupdf

    words = [w for w in query.split() if len(w) > 2]
    tries = [query.strip()] + (words if len(words) > 1 else [])
    out: list[dict] = []
    total = 0
    with pymupdf.open(p) as doc:
        for text in tries:
            if not text:
                continue
            for i in range(doc.page_count):
                page = doc[i]
                rects = page.search_for(text)
                if not rects:
                    continue
                w, h = page.rect.width, page.rect.height
                hit = next((o for o in out if o["page"] == i), None)
                if hit is None:
                    hit = {"page": i, "rects": []}
                    out.append(hit)
                for r in rects:
                    hit["rects"].append([r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h])
                    total += 1
                    if total >= MAX_MATCHES:
                        return sorted(out, key=lambda o: o["page"])
            if out:  # the whole phrase was found: no need for single words
                break
    return sorted(out, key=lambda o: o["page"])
