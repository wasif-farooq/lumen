"""Runs the indexer for the app: as a low-priority subprocess, with live progress, pause and stop."""

import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from ...core import logging as lumen_logging
from ...core.filetypes import kind_of
from ...core.settings import settings
from ...indexing.progress import EVENT_PREFIX, parse_event

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self):
        self.proc = None
        self.lines = deque(maxlen=300)
        self.started = None
        self.stopping = False
        self.pause_file = settings.data_dir / "index.pause"
        self.pause_file.unlink(missing_ok=True)  # a flag left by a crash would hold the next run
        self._reset()

    def _reset(self):
        self.state = {"phase": None, "done": 0, "total": 0, "path": None, "note": None, "scanned": 0,
                      "ext": None, "kind": None, "paused": False, "summary": None, "error": None}
        self.recent = deque(maxlen=8)  # last files finished: {phase, path, note}
        self.phase_started = time.time()
        self.paused_since = None
        self.paused_in_phase = 0.0  # seconds, so the time-left estimate ignores pauses

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def pause_requested(self) -> bool:
        return self.pause_file.exists()

    def start(self):
        if self.running:
            return
        self.pause_file.unlink(missing_ok=True)
        self.lines.clear()
        self._reset()
        self.started = time.time()
        self.stopping = False
        # Separate process: its low priority (nice/ionice) never slows the API or chat
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lumen", "index"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "COLUMNS": "200", "LUMEN_DATA": str(settings.data_dir), "PYTHONUNBUFFERED": "1",
                 "LUMEN_EVENTS": "1", "LUMEN_PAUSE_FILE": str(self.pause_file)},
            start_new_session=True,  # own process group, so Stop also ends its ffmpeg children
        )
        log.info("indexing started (pid %s): %s", self.proc.pid, ", ".join(map(str, settings.roots)))
        threading.Thread(target=self._pump, daemon=True).start()

    def pause(self) -> bool:
        """Ask indexing to hold after the file it is on. It saves its work first, so the
        database is never locked while paused."""
        if not self.running:
            return False
        self.pause_file.touch()
        return True

    def resume(self) -> bool:
        self.pause_file.unlink(missing_ok=True)
        return self.running

    def stop(self) -> bool:
        """Stop indexing. Work already saved stays; the next run continues with what is left."""
        self.pause_file.unlink(missing_ok=True)
        if not self.running:
            return False
        import signal

        self.stopping = True
        log.info("indexing stopped from the app")
        pgid = os.getpgid(self.proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            self.proc.wait(timeout=5)
        self.lines.append("Stopped. Finished work is saved; the next run continues with the rest.")
        return True

    def _event(self, e: dict):
        st, now = self.state, time.time()
        if "phase" in e:
            st.update(phase=e["phase"], done=0, total=0, path=None, note=None)
            self.phase_started, self.paused_in_phase = now, 0.0
        if "scanned" in e:
            st["scanned"] = e["scanned"]
        if "item" in e:
            it = e["item"]
            ext = Path(it["path"]).suffix.lower().lstrip(".")
            st.update(done=it["done"], total=it["total"], path=it["path"], note=it["note"], ext=ext, kind=kind_of(ext))
            entry = {"phase": st["phase"], "path": it["path"], "note": it["note"], "ext": ext, "kind": st["kind"]}
            if self.recent and self.recent[0]["path"] == it["path"]:
                self.recent[0] = entry  # video/audio report several steps for one file
            else:
                self.recent.appendleft(entry)
        if "paused" in e:
            st["paused"] = bool(e["paused"])
            if st["paused"]:
                self.paused_since = now
            elif self.paused_since:
                self.paused_in_phase += now - self.paused_since
                self.paused_since = None
        if "summary" in e:
            st["summary"] = e["summary"]

    def _pump(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            if line.startswith(EVENT_PREFIX):  # progress for the app; a garbled one is dropped
                event = parse_event(line)
                try:
                    if event:
                        self._event(event)
                except (KeyError, TypeError):
                    pass
            elif line and "onnxruntime" not in line and "HF Hub" not in line:
                self.lines.append(line)
        self.pause_file.unlink(missing_ok=True)
        self.state["paused"] = False
        self._finished(self.proc.wait())

    def _finished(self, code: int):
        """Log how the run ended; a crash becomes an error the app shows."""
        if code == 0 or self.stopping:
            log.info("indexing finished (exit %s)", code)
            return
        last = next((ln for ln in reversed(self.lines) if ln.strip()), "")
        log.error("indexing ended with exit %s: %s", code, last)
        self.state["error"] = (f"Indexing stopped unexpectedly{f': {last}' if last else ''}. "
                               f"Details: {lumen_logging.log_file('indexer')}")

    def progress(self) -> dict:
        st = self.state
        eta = None
        if self.running and st["total"] and 0 < st["done"] < st["total"]:
            paused = self.paused_in_phase + (time.time() - self.paused_since if self.paused_since else 0)
            active = time.time() - self.phase_started - paused
            eta = round(active / st["done"] * (st["total"] - st["done"]))
        return {"running": self.running, "started": self.started, **st,
                "pausing": self.running and self.pause_requested and not st["paused"],
                "eta": eta, "recent": list(self.recent), "lines": list(self.lines)}
