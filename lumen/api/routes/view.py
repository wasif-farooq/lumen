"""Reading files in the app (the viewer): what a file is, PDF pages and matches, full-size images,
text in pieces, documents as blocks, and media streamed with seeking. Only files in the indexed
folders, and not those kept out of the index (Settings → Sync)."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response

from ...core import errors
from ...core.settings import settings
from ...viewer import blocks, kinds, pdf, text
from .. import thumbnails
from ..deps import auth, checked_path

PAGE_MIN, PAGE_MAX = 200, 2400  # page widths the app may ask for (pixels)
IMAGE_MAX = 4096

router = APIRouter(dependencies=[Depends(auth)])


def viewable(path: str) -> Path:
    """A file the viewer may show: inside the indexed folders, not excluded, a file; or a mail
    attachment fetched for the viewer."""
    cache = (settings.data_dir / "mail-cache").resolve()
    p = Path(path).resolve()
    if p.is_relative_to(cache) and p != cache:
        if not p.is_file():
            raise errors.NotFound("File not found")
        return p
    p = checked_path(path)
    if any(p == Path(e) or p.is_relative_to(Path(e)) for e in settings.excluded):
        raise errors.OutsideFolders("This file is kept out of Lumen (Settings → Sync).")
    if not p.is_file():
        raise errors.InvalidInput("Only files can be viewed.")
    return p


@router.get("/api/view")
def describe(path: str) -> dict:
    return kinds.describe(viewable(path))


@router.get("/api/view/page")
def page(path: str, page: int = 0, w: int = 1200) -> Response:
    p = viewable(path)
    if kinds.kind(p.suffix.lower().lstrip(".")) != "pdf":
        raise errors.InvalidInput("Pages are for PDFs.")
    if not 0 <= page < pdf.page_count(p):
        raise errors.NotFound(f"No page {page + 1}.")
    png = thumbnails.cached(p, max(PAGE_MIN, min(w, PAGE_MAX)), page=page)
    if png is None:
        raise errors.NotFound("This page can't be shown.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.get("/api/view/find")
def find(path: str, q: str) -> list[dict]:
    p = viewable(path)
    return pdf.find(p, q) if q.strip() and p.suffix.lower() == ".pdf" else []


@router.get("/api/view/page-text")
def page_text(path: str, page: int = 0) -> dict:
    return {"page": page, "text": pdf.page_text(viewable(path), page)}


@router.get("/api/view/image")
def image(path: str, w: int = 2000) -> Response:
    p = viewable(path)
    if kinds.kind(p.suffix.lower().lstrip(".")) != "image":
        raise errors.InvalidInput("Not an image.")
    png = thumbnails.cached(p, max(PAGE_MIN, min(w, IMAGE_MAX)), upscale=False)
    if png is None:
        raise errors.NotFound("This image can't be shown.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.get("/api/view/text")
def text_piece(path: str, offset: int = 0, limit: int = text.PIECE) -> dict:
    p = viewable(path)
    if kinds.kind(p.suffix.lower().lstrip(".")) not in ("text", "markdown", "code"):
        raise errors.InvalidInput("Not a text file.")
    return text.piece(p, offset, limit)


@router.get("/api/view/blocks")
def document(path: str) -> dict:
    p = viewable(path)
    ext = p.suffix.lower().lstrip(".")
    if kinds.kind(ext) not in ("document", "table", "slides"):
        raise errors.InvalidInput("Not a document, spreadsheet or presentation.")
    try:
        return blocks.blocks(p, ext)
    except Exception as e:  # damaged or password-protected
        raise errors.InvalidInput(f"This file can't be read: {e}") from e


@router.get("/api/view/stream")
def stream(path: str) -> FileResponse:
    """The file itself, for video and audio; seeking uses HTTP Range (206 Partial Content)."""
    p = viewable(path)
    if kinds.kind(p.suffix.lower().lstrip(".")) not in ("video", "audio"):
        raise errors.InvalidInput("Only video and audio are streamed.")
    return FileResponse(p, filename=p.name, content_disposition_type="inline")
