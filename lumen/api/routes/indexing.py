"""Index runs (start, pause, resume, stop, progress) and what gets indexed (exclusions, folders)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ...core import preferences
from ...core.settings import settings
from ...storage import catalog
from ..deps import auth, local_only, services
from ..schemas import PathBody
from ..services import Services

router = APIRouter()


@router.post("/api/index", dependencies=[Depends(auth)])
def run_index(svc: Services = Depends(services)):
    svc.indexer.start()
    return {"running": True}


@router.post("/api/index/stop", dependencies=[Depends(auth)])
def stop_index(svc: Services = Depends(services)):
    return {"stopped": svc.indexer.stop(), "running": svc.indexer.running}


@router.post("/api/index/pause", dependencies=[Depends(auth)])
def pause_index(svc: Services = Depends(services)):
    return {"pausing": svc.indexer.pause(), "running": svc.indexer.running}


@router.post("/api/index/resume", dependencies=[Depends(auth)])
def resume_index(svc: Services = Depends(services)):
    return {"running": svc.indexer.resume()}


@router.get("/api/index", dependencies=[Depends(auth)])
def index_progress(svc: Services = Depends(services)):
    return svc.indexer.progress()


def _not_while_indexing(svc: Services):
    # A running index already read the folder list and exclusions, so it would undo the change
    if svc.indexer.running:
        raise HTTPException(409, "Indexing is running. Wait for it to finish, or stop it, then try again.")


def _root(path: str) -> Path:
    r = Path(path).expanduser().resolve()
    if r not in settings.roots:
        raise HTTPException(404, f"Not an indexed folder: {r}")
    return r


@router.post("/api/index/exclude", dependencies=[Depends(local_only)])
def exclude_path(body: PathBody, svc: Services = Depends(services)):
    """Drop a file or folder from the index and keep it out of later runs."""
    _not_while_indexing(svc)
    p = Path(body.path).expanduser().resolve()
    if not any(p.is_relative_to(r) for r in settings.roots):
        raise HTTPException(400, f"Not inside an indexed folder: {p}")
    if p in settings.roots:
        raise HTTPException(400, "To drop a whole folder, remove it from the folder list instead")
    removed = catalog.forget(str(p))
    preferences.update({"excluded": [*settings.excluded, str(p)]})
    return {"removed": removed, "excluded": settings.excluded}


@router.post("/api/index/include", dependencies=[Depends(local_only)])
def include_path(body: PathBody, svc: Services = Depends(services)):
    """Let an excluded file or folder back in; it is indexed on the next run (now, by default)."""
    _not_while_indexing(svc)
    p = str(Path(body.path).expanduser().resolve())
    preferences.update({"excluded": [e for e in settings.excluded if e != p]})
    if body.reindex:
        svc.indexer.start()
    return {"excluded": settings.excluded}


@router.post("/api/folders/pause", dependencies=[Depends(local_only)])
def pause_folder(body: PathBody, svc: Services = Depends(services)):
    """Keep a folder's files searchable but stop re-scanning it."""
    _not_while_indexing(svc)
    r = _root(body.path)
    preferences.update({"paused_roots": [*(p for p in settings.paused_roots if p != r), r]})
    return {"paused": True}


@router.post("/api/folders/resume", dependencies=[Depends(local_only)])
def resume_folder(body: PathBody, svc: Services = Depends(services)):
    _not_while_indexing(svc)
    r = _root(body.path)
    preferences.update({"paused_roots": [p for p in settings.paused_roots if p != r]})
    if body.reindex:
        svc.indexer.start()  # catch up on what changed while it was paused
    return {"paused": False}


@router.post("/api/folders/clear", dependencies=[Depends(local_only)])
def clear_folder(body: PathBody, svc: Services = Depends(services)):
    """Drop everything indexed under a folder. The files themselves are not touched."""
    _not_while_indexing(svc)
    r = _root(body.path)
    removed = catalog.forget(str(r))
    if body.reindex and r not in settings.paused_roots:
        svc.indexer.start()
    return {"removed": removed}
