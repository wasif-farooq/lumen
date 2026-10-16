"""What the app shows about this laptop: the index, folders, power, models; and the settings."""

import json
import logging
import os
import socket

from fastapi import APIRouter, Depends

from ...core import errors, preferences
from ...core.settings import settings
from ...indexing import power
from ...providers import registry
from ...storage import catalog
from ..deps import auth, local_only, services
from ..services import Services

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/status", dependencies=[Depends(auth)])
def status(svc: Services = Depends(services)):
    try:
        last = json.loads((settings.data_dir / "last_index.json").read_text())
    except (OSError, ValueError):
        last = None
    try:
        import ollama

        loaded = [m.model for m in ollama.Client(host=settings.ollama_host).ps().models]
        ollama_ok = True
    except Exception as e:  # Ollama not running (or not installed): the status says so
        log.debug("ollama status: %s", e)
        loaded, ollama_ok = [], False
    ai_allowed, why = power.heavy_allowed()
    agent, vision = registry.get(settings.agent_provider), registry.get(settings.vision_provider)
    return {
        "host": socket.gethostname(),
        "index": catalog.stats(),
        "last_index": last,
        "indexing": svc.indexer.running,
        "index_paused": svc.indexer.state["paused"],
        "folders": [
            {"path": str(r), "files": catalog.count_under(r), "paused": r in settings.paused_roots}
            for r in settings.roots
        ],
        "power": {
            "on_ac": power.on_ac(),
            "battery": power.battery_percent(),
            "mode": settings.power_mode,
            "ai_allowed": ai_allowed,
            "reason": why,
            "threads": power.threads(),
        },
        "models": {
            "agent": settings.agent_model,
            "vision": settings.caption_model,
            "speech": f"whisper-{settings.whisper_model}",
            "agent_provider": agent["name"],
            "vision_provider": vision["name"],
            "agent_cloud": registry.is_cloud(agent),
            "vision_cloud": registry.is_cloud(vision),
            "cpu_only": settings.cpu_only,
            "ollama_ok": ollama_ok,
            "loaded": loaded,
        },
        "langfuse": bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
        "langfuse_host": os.environ.get("LANGFUSE_HOST", ""),
        "lan": svc.lan,
        "open_mode": settings.open_mode,
    }


@router.get("/api/settings", dependencies=[Depends(auth)])
def get_settings():
    return preferences.current()


@router.put("/api/settings", dependencies=[Depends(local_only)])
def put_settings(body: dict, svc: Services = Depends(services)):
    before = settings.cpu_only
    if "roots" in body:
        try:
            preferences.check_roots(body["roots"])
        except ValueError as e:
            raise errors.InvalidInput(str(e)) from e
    roots_before = list(settings.roots)
    out = preferences.update(body)
    if settings.cpu_only != before or settings.roots != roots_before:
        svc.chats.forget_sessions()  # rebuild agents with the new GPU/CPU choice / folder list
    return out


@router.get("/api/diagnostics", dependencies=[Depends(local_only)])
def diagnostics(svc: Services = Depends(services)):
    """For a bug report: versions, which model does what, where the logs are and their last lines.
    No keys. Only on the laptop (the logs name files)."""
    import platform
    from importlib import metadata

    from ...core import logging as lumen_logging

    def tail(component: str, n: int = 200) -> list[str]:
        try:
            return lumen_logging.log_file(component).read_text(errors="replace").splitlines()[-n:]
        except OSError:
            return []

    try:
        version = metadata.version("lumen")
    except metadata.PackageNotFoundError:
        version = "dev"
    return {
        "version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "roles": registry.roles(),
        "power_mode": settings.power_mode,
        "cpu_only": settings.cpu_only,
        "folders": len(settings.roots),
        "indexing": svc.indexer.running,
        "log_dir": str(lumen_logging.log_dir()),
        "logs": {c: tail(c) for c in lumen_logging.FILES},
    }
