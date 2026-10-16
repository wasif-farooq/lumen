"""Pictures: search by what they show, similar images, and photos dropped on a chat."""

import hashlib
import logging
from io import BytesIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ...core import errors
from ...core.settings import settings
from ...search import images
from ...search.hybrid import hybrid_image_search, image_hits
from ...storage import db
from ...storage.chats import NEW_TITLE
from ..deps import auth, checked_path, services
from ..schemas import SimilarReq
from ..services import Services

log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(auth)])
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


@router.get("/api/images/search")
def image_search(q: str, folder: str = "", limit: int = 12):
    conn = db.connect()
    try:
        return hybrid_image_search(conn, q, limit=min(max(limit, 1), 50), folder=folder)
    finally:
        conn.close()


@router.get("/api/images/similar")
def image_similar(path: str):
    p = checked_path(path)
    conn = db.connect()
    try:
        return image_hits(conn, images.similar_to(conn, str(p)))
    finally:
        conn.close()


@router.post("/api/chats/{chat_id}/similar")
def chat_similar(chat_id: str, body: SimilarReq, svc: Services = Depends(services)):
    p = checked_path(body.path)
    return _similar_and_log(svc, chat_id, str(p), {"text": f"Images like {p.name}", "image_path": str(p)})


@router.post("/api/chats/{chat_id}/similar-upload")
async def chat_similar_upload(chat_id: str, request: Request, svc: Services = Depends(services)):
    """Raw image bytes in the body (a dropped file or a phone photo); the photo is kept, downscaled,
    so the chat can show it."""
    data = await request.body()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise errors.InvalidInput("Send one image up to 30 MB")
    try:
        im = images.open_image(data)
    except Exception as e:
        log.info("upload is not an image: %s", e)
        raise errors.InvalidInput("That file is not an image I can read") from e
    im = im.convert("RGB")
    im.thumbnail((1024, 1024))
    upload_id = hashlib.sha1(data).hexdigest()[:20]
    folder = settings.data_dir / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=88)
    (folder / f"{upload_id}.jpg").write_bytes(buf.getvalue())
    return _similar_and_log(svc, chat_id, buf.getvalue(), {"text": "Images like this photo", "upload": upload_id})


@router.get("/api/uploads/{upload_id}")
def get_upload(upload_id: str):
    if not upload_id.isalnum():
        raise errors.InvalidInput("Bad id")
    f = settings.data_dir / "uploads" / f"{upload_id}.jpg"
    if not f.exists():
        raise errors.NotFound("Not found")
    return Response(f.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


def _similar_and_log(svc: Services, chat_id: str, source, label: dict) -> list[dict]:
    """Run a similar-image search for an app button/upload and record it in the chat."""
    title = svc.chats.store.title(chat_id)
    if title is None:
        raise errors.NotFound("No such chat")
    conn = db.connect()
    try:
        hits = image_hits(conn, images.similar_to(conn, source))
    finally:
        conn.close()
    if title == NEW_TITLE:
        svc.chats.store.set_title(chat_id, label["text"][:48])
    svc.chats.log(chat_id, "user", label)
    svc.chats.log(chat_id, "results", {"hits": hits})
    # so "open the second one" in the next message refers to these
    svc.chats.session(chat_id).state.setdefault("last_results", [])[:] = [h["path"] for h in hits]
    return hits
