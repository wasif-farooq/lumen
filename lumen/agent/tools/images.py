"""Pictures by what they show, and pictures that look alike."""

from langchain_core.tools import tool

from ...search import images
from ...search.hybrid import hybrid_image_search, image_hits
from ...storage import db
from .context import ToolContext


def build(ctx: ToolContext) -> dict:
    last_results, emit, resolve = ctx.last_results, ctx.emit, ctx.resolve

    @tool
    def search_images(description: str, folder: str = "") -> str:
        """Find photos/images by what they SHOW, e.g. "sunset at the beach", "my passport", "a red car",
        "screenshots of code". Matches how images look, not only file names.

        Args:
            description: what is in the picture.
            folder: only images whose path contains this text (optional).
        """
        conn = db.connect()
        try:
            hits = hybrid_image_search(conn, description, folder=folder)
        finally:
            conn.close()
        last_results[:] = [h["path"] for h in hits]
        emit({"type": "results", "hits": hits})
        if not hits:
            return "No matching images."
        return "\n".join(
            f"{i}. {h['name']}  path: {h['path']}\n   shows: {h['snippet'][:160]}" for i, h in enumerate(hits, 1)
        )

    @tool
    def find_similar_images(target: str) -> str:
        """Find images that look like a given image (same scene, person, document type...).

        Args:
            target: full image path, or a result number from the last results (e.g. "1").
        """
        path = resolve(target)
        conn = db.connect()
        try:
            hits = image_hits(conn, images.similar_to(conn, str(path)))
        finally:
            conn.close()
        last_results[:] = [h["path"] for h in hits]
        emit({"type": "results", "hits": hits})
        if not hits:
            return f"No images look like {path.name}."
        return f"Images that look like {path.name}:\n" + "\n".join(
            f"{i}. {h['name']}  path: {h['path']}  similarity {h['score']}" for i, h in enumerate(hits, 1)
        )

    # ---- changes: each one pauses for the user's approval (LangGraph interrupt) ----

    return {"search_images": search_images, "find_similar_images": find_similar_images}
