"""Files: search, details, previews, and opening them on the desktop."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ...core import errors
from ...core.filetypes import MEDIA_EXTS, RUNNABLE_EXTS, kind_of
from ...core.formatting import fmt_time
from ...fileops.access import launch
from ...search import text as text_search
from ...storage import catalog, db
from .. import thumbnails
from ..deps import auth, checked_path
from ..responses import FileInfoOut, HitOut, Message, SegmentOut
from ..schemas import OpenReq

EXCERPT_CHARS = 1500  # text shown in the preview panel
THUMB_MIN, THUMB_MAX = 64, 1600  # thumbnail widths the app may ask for (pixels)

router = APIRouter(dependencies=[Depends(auth)])


@router.get("/api/search")
def search(
    q: str = "",
    ext: str = "",
    after: str = "",
    before: str = "",
    folder: str = "",
    limit: int = 20,
    min_minutes: float = 0,
    max_minutes: float = 0,
) -> list[HitOut]:
    hits = text_search.search_all(q, ext, after, before, folder, min(max(limit, 1), 100), min_minutes, max_minutes)
    return [HitOut.model_validate(h.to_dict()) for h in hits]


@router.get("/api/file")
def file_info(path: str, at: float | None = None) -> FileInfoOut:
    p = checked_path(path)
    st = p.stat()
    ext = p.suffix.lower().lstrip(".")
    conn = db.connect()
    try:
        row = conn.execute("SELECT id, caption, duration, has_text FROM files WHERE path=?", (str(p),)).fetchone()
        segments: list[SegmentOut] = []
        if row and ext in MEDIA_EXTS:
            if at is not None:
                q = "SELECT start, end, text FROM segments WHERE file_id=? AND start BETWEEN ? AND ? ORDER BY start"
                segs = conn.execute(q, (row["id"], at - 30, at + 60)).fetchall()
            else:
                segs = conn.execute(
                    "SELECT start, end, text FROM segments WHERE file_id=? ORDER BY start LIMIT 300", (row["id"],)
                ).fetchall()
            segments = [
                SegmentOut(start=s["start"], end=s["end"], text=s["text"], time=fmt_time(s["start"])) for s in segs
            ]
    finally:
        conn.close()
    text = catalog.indexed_text(str(p))
    return FileInfoOut(
        path=str(p),
        name=p.name,
        ext=ext,
        kind=kind_of(ext),
        size=st.st_size,
        mtime=st.st_mtime,
        folder=str(p.parent),
        indexed=row is not None,
        searchable=bool(row and (row["has_text"] or row["caption"])),
        caption=(row["caption"] if row else "") or "",
        duration=row["duration"] if row else None,
        excerpt=text[:EXCERPT_CHARS],
        segments=segments,
    )


@router.get("/api/thumb")
def thumb(path: str, w: int = 480, t: float | None = None) -> Response:
    p = checked_path(path)
    png = thumbnails.cached(p, max(THUMB_MIN, min(w, THUMB_MAX)), t)
    if png is None:
        raise errors.NotFound("No preview for this file type")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.post("/api/open")
def open_file(body: OpenReq) -> Message:
    p = checked_path(body.path)
    ext = p.suffix.lower().lstrip(".")
    if p.is_file() and (ext in RUNNABLE_EXTS or os.access(p, os.X_OK)):
        return Message(ok=True, message="Scripts and programs open their folder instead. " + launch(p.parent))
    return Message(ok=True, message=launch(p, body.start_seconds if ext in MEDIA_EXTS else 0))


@router.post("/api/show")
def show_in_folder(body: OpenReq) -> Message:
    p = checked_path(body.path)
    return Message(ok=True, message=launch(p if p.is_dir() else p.parent))
