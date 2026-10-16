"""Keep indexing cheap: low CPU/IO priority, few threads, and no heavy AI work on battery.

Modes (LUMEN_POWER):
  auto        (default) heavy passes (captions, video, speech) only while plugged in
  saver       never run heavy passes; just files + document text
  performance always run everything, with more threads
"""

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from ..core.settings import settings

log = logging.getLogger(__name__)



SUPPLY = Path("/sys/class/power_supply")


def on_ac() -> bool:
    """True when plugged in, or when the machine has no battery at all."""
    if not SUPPLY.is_dir():
        return True
    has_battery = False
    for dev in SUPPLY.iterdir():
        kind = _read(dev / "type")
        if kind == "Battery":
            has_battery = True
        elif kind in ("Mains", "USB") and _read(dev / "online") == "1":
            return True
    return not has_battery


def battery_percent() -> int | None:
    for dev in SUPPLY.glob("BAT*"):
        value = _read(dev / "capacity")
        if value.isdigit():
            return int(value)
    return None


def heavy_allowed() -> tuple[bool, str]:
    """May we run the AI passes right now? Returns (allowed, reason when not)."""
    if settings.power_mode == "performance":
        return True, ""
    if settings.power_mode == "saver":
        return False, "power mode is 'saver'"
    if not on_ac():
        pct = battery_percent()
        return False, f"on battery{f' ({pct}%)' if pct is not None else ''}; will run when plugged in"
    return True, ""


def threads() -> int:
    if settings.power_mode == "performance":
        return max(1, (os.cpu_count() or 4) - 2)
    return settings.threads


def low_priority():
    """Lowest CPU priority and idle-only disk IO for this process and everything it starts."""
    try:
        os.nice(19 - os.nice(0))
    except OSError:
        pass
    if shutil.which("ionice"):
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], capture_output=True)
    # Math libraries (whisper/onnx/numpy) read these when they start
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, str(threads()))


on_pause = None  # called with True/False when indexing holds for / leaves a pause


def wait_if_paused() -> None:
    """Hold here while the app has paused indexing. The app creates the flag file named in
    LUMEN_PAUSE_FILE; callers only call this between files, after their last commit."""
    flag = os.environ.get("LUMEN_PAUSE_FILE")
    if not flag or not os.path.exists(flag):
        return
    if on_pause:
        on_pause(True)
    while os.path.exists(flag):
        time.sleep(0.5)
    if on_pause:
        on_pause(False)


def wait_until_idle(max_wait: float = 300) -> None:
    """Before each heavy item: if the machine is busy (user working), wait a bit for it to calm down."""
    wait_if_paused()
    if settings.power_mode == "performance":
        return
    limit = (os.cpu_count() or 4) * 0.6
    waited = 0.0
    while os.getloadavg()[0] > limit and waited < max_wait:
        time.sleep(10)
        waited += 10


class GpuModel:
    """Unload the vision model after indexing, but only if indexing is what loaded it
    (so an open chat keeps its warm model)."""

    def __init__(self, model: str):
        self.model = model
        self.was_loaded = True

    def __enter__(self):
        try:
            import ollama

            loaded = ollama.Client(host=settings.ollama_host).ps().models
            self.was_loaded = any(m.model == self.model or m.name == self.model for m in loaded)
        except Exception as e:  # no Ollama: nothing to unload later
            log.debug("ollama ps: %s", e)
        return self

    def __exit__(self, *exc):
        if self.was_loaded:
            return
        try:
            import ollama

            ollama.Client(host=settings.ollama_host).generate(
                model=self.model, prompt="", keep_alive=0, options=settings.ollama_options()
            )
        except Exception as e:
            log.debug("unloading %s: %s", self.model, e)


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""
