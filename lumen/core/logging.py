"""Logging for every part of Lumen: one logger per module, written to rotating files.

    ~/.local/state/lumen/lumen.log     the server (API, chats, model calls)
    ~/.local/state/lumen/indexer.log   index runs
    ~/.local/state/lumen/cli.log       terminal commands

LUMEN_LOG_LEVEL sets how much is written (DEBUG, INFO, WARNING, ERROR; default INFO).
LUMEN_LOG_DIR moves the folder. Each line carries the request id while a request is handled,
so a "Something went wrong (id …)" in the app leads to the matching lines.
"""

import contextvars
import logging
import logging.handlers
import os
from pathlib import Path

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s"
FILES = {"server": "lumen.log", "indexer": "indexer.log", "cli": "cli.log"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def log_dir() -> Path:
    if os.environ.get("LUMEN_LOG_DIR"):
        return Path(os.environ["LUMEN_LOG_DIR"]).expanduser()
    return Path(os.environ.get("XDG_STATE_HOME") or "~/.local/state").expanduser() / "lumen"


def log_file(component: str) -> Path:
    return log_dir() / FILES[component]


def setup(component: str, console: bool = False) -> Path:
    """Send the `lumen` loggers to this component's file (and to stderr with `console`).
    Safe to call again: earlier handlers are replaced."""
    level = getattr(logging, os.environ.get("LUMEN_LOG_LEVEL", "INFO").upper(), logging.INFO)
    root = logging.getLogger("lumen")
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(level)
    root.propagate = False
    formatter = logging.Formatter(FORMAT)
    path = log_file(component)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3,
                                                                        encoding="utf-8")
    except OSError:  # a read-only home (some sandboxes): log to stderr rather than not at all
        handler = logging.StreamHandler()
    handlers = [handler] + ([logging.StreamHandler()] if console else [])
    for h in handlers:
        h.setFormatter(formatter)
        h.addFilter(_RequestIdFilter())
        root.addHandler(h)
    return path
