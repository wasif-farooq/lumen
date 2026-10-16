"""Images matching a description: what they look like (CLIP) fused with their AI description."""

import sqlite3

from ..core.filetypes import IMAGE_EXTS
from . import images
from . import text as text_search


def image_hits(conn: sqlite3.Connection, scored: list[tuple[dict, float]]) -> list[dict]:
    """Result-card dicts for visual matches, with each image's AI description as the snippet."""
    out = []
    for r, score in scored:
        row = conn.execute("SELECT caption FROM files WHERE path=?", (r["path"],)).fetchone()
        caption = (row["caption"] if row else "") or ""
        hit = text_search.Hit(r["path"], r["name"], r["ext"], r["size"], r["mtime"], caption[:200]).to_dict()
        hit["score"] = round(score, 3)
        out.append(hit)
    return out


def hybrid_image_search(conn: sqlite3.Connection, description: str, limit: int = 8, folder: str = "") -> list[dict]:
    """Images matching a description: what they look like (CLIP) fused with their AI description (text)."""
    by_look = images.search_text(conn, description, k=limit * 2, folder=folder)
    by_text = text_search.search(description, ext=",".join(sorted(IMAGE_EXTS)), folder=folder, limit=limit * 2)
    score, info = {}, {}
    for rank, (r, s) in enumerate(by_look):  # reciprocal rank fusion
        score[r["path"]] = score.get(r["path"], 0) + 1 / (10 + rank)
        info[r["path"]] = (r, s)
    for rank, h in enumerate(by_text):
        if h.partial:
            continue
        score[h.path] = score.get(h.path, 0) + 1 / (10 + rank)
        info.setdefault(h.path, ({"path": h.path, "name": h.name, "ext": h.ext, "size": h.size, "mtime": h.mtime}, 0.0))
    best = sorted(score, key=lambda p: -score[p])[:limit]
    return image_hits(conn, [info[p] for p in best])
