"""Reminders going off: a thread in `lumen serve` checks every few seconds and, when one is due,
shows a desktop notification, says it on any open voice chat, and leaves it for the app's banner
until the user deals with it. Repeating reminders move on to their next time.

A reminder whose time passed while the server was off goes off once at start ("Missed: ...");
a repeating one then continues from its next time after now (it doesn't fire once per missed day).
"""

import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime

from ..core.settings import settings
from .store import PlannerStore
from .times import next_after

log = logging.getLogger(__name__)

LATE = 120  # seconds: later than this, a reminder counts as missed (the server was off)


def desktop_notify(title: str, body: str) -> None:
    """A notification on the laptop's desktop: notify-send (libnotify), or straight to the desktop's
    notification service with gdbus (part of GLib, there even when libnotify-bin isn't)."""
    if exe := shutil.which("notify-send"):
        cmd = [exe, "-a", "Lumen", "-i", "appointment-soon", "-u", "normal", title, body]
    elif exe := shutil.which("gdbus"):  # the timeout is in ms ("-1" would be read as an option)
        cmd = [exe, "call", "--session", "--dest", "org.freedesktop.Notifications",
               "--object-path", "/org/freedesktop/Notifications", "--method", "org.freedesktop.Notifications.Notify",
               "Lumen", "0", "appointment-soon", title, body, "[]", "{}", "10000"]  # fmt: skip
    else:
        if not getattr(desktop_notify, "warned", False):
            log.warning("no notify-send or gdbus: reminders show in the app only (install libnotify-bin)")
            desktop_notify.warned = True  # type: ignore[attr-defined]
        return
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        if r.returncode != 0:
            log.warning("desktop notification failed: %s", r.stderr.strip()[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("desktop notification failed: %s", e)


class ReminderScheduler:
    def __init__(
        self,
        store: Callable[[], PlannerStore],
        notify: Callable[[str, str], None] = desktop_notify,
        now: Callable[[], float] = time.time,
        every: float = 15,
    ) -> None:
        self.store, self.notify, self.now, self.every = store, notify, now, every
        self.speakers: list[Callable[[str], None]] = []  # open voice chats
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("checking reminders failed")
            self._stop.wait(self.every)

    def tick(self) -> list[dict]:
        """Fire every reminder that is due now; returns them (for tests and logs)."""
        now = self.now()
        fired = []
        for r in self.store().due(now):
            missed = now - r["next_at"] > LATE
            text = ("Missed: " if missed else "") + r["text"]
            if settings.reminder_notify:
                self.notify("Reminder", text)
            if settings.reminder_speak:
                for speak in list(self.speakers):
                    try:
                        speak(f"Reminder: {text}")
                    except Exception:
                        log.exception("saying a reminder failed")
            next_at = None
            if r["repeat"] != "none":
                anchor = datetime.fromtimestamp(r["at"])
                next_at = next_after(anchor, r["repeat"], datetime.fromtimestamp(now)).timestamp()
            self.store().fired(r["id"], now, next_at)
            log.info("reminder %s went off%s", r["id"], " (missed)" if missed else "")
            fired.append({**r, "text": text, "missed": missed})
        return fired
