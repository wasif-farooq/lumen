"""Notes, to-dos and reminders.

notes      Markdown notes in the notes folder (the user's own files)
store      to-do lists, to-dos and reminders (planner.db)
times      plain words to times ("tomorrow at 5", "every Monday 9am")
scheduler  reminders going off (desktop notification, voice, the app's banner)
"""

import threading
from pathlib import Path

from ..core.settings import settings
from .store import PlannerStore

_stores: dict[Path, PlannerStore] = {}
_lock = threading.Lock()


def store() -> PlannerStore:
    """The planner database in the current data folder (one connection per folder)."""
    path = settings.data_dir / "planner.db"
    with _lock:
        if path not in _stores:
            _stores[path] = PlannerStore(path)
        return _stores[path]
