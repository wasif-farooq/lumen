"""Downloading Ollama models in the background, with progress the app can show."""

import logging
import threading

from ..core.settings import settings
from . import backends

log = logging.getLogger(__name__)


_pulls: dict[str, dict] = {}  # model -> {status, completed, total, done, error}


def pull(model: str) -> dict:
    """Start downloading an Ollama model in the background; poll pull_status()."""
    model = model.strip()
    if not model:
        raise ValueError("Enter a model name, e.g. qwen2.5vl:3b")
    cur = _pulls.get(model)
    if cur and not cur["done"]:
        return cur
    st = _pulls[model] = {"model": model, "status": "starting", "completed": 0, "total": 0, "done": False, "error": None}

    def run():
        import ollama

        try:
            for ev in ollama.Client(host=settings.providers["ollama"]["base_url"]).pull(model, stream=True):
                st.update(status=ev.status or st["status"], completed=ev.completed or st["completed"], total=ev.total or st["total"])
            st["status"] = "done"
        except Exception as e:
            log.warning("download of %s failed: %s", model, e)
            st["error"] = backends.why(e) if not isinstance(e, ollama.ResponseError) else str(e.error)
        finally:
            st["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return st


def pull_status() -> list[dict]:
    return list(_pulls.values())
