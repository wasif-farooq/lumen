"""Shared test setup.

Every test runs against its own temporary data folder and a small folder of sample files, with
the AI passes off and Ollama pointed at an address where nothing listens, so tests are offline,
fast and never touch the real index. Chat tests use a scripted fake model.

This is the only file that knows Lumen's internal module layout: when code moves during the
refactor, only this file changes, and the tests themselves keep pinning the same behaviour.
"""

import os
import tempfile
import time
from pathlib import Path

# Before Lumen is imported: config reads these once at import time.
_BOOT = Path(tempfile.mkdtemp(prefix="lumen-tests-"))
for key, value in {
    "LUMEN_DATA": str(_BOOT / "data"),
    "LUMEN_LOG_DIR": str(_BOOT / "logs"),
    "LUMEN_ROOTS": str(_BOOT / "roots"),
    "LUMEN_POWER": "saver",
    "LUMEN_CAPTIONS": "0",
    "LUMEN_MEDIA": "0",
    "LUMEN_VISUAL": "0",
    "LUMEN_OPEN_MODE": "print",
    "OLLAMA_HOST": "http://127.0.0.1:9",
}.items():
    os.environ[key] = value
for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
    os.environ.pop(key, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import Field  # noqa: E402

from lumen.agent.tools import make_tools  # noqa: E402
from lumen.api.app import create_app  # noqa: E402
from lumen.core.settings import settings  # noqa: E402
from lumen.indexing.passes import speech as speech_pass  # noqa: E402
from lumen.indexing.pipeline import build_index  # noqa: E402
from lumen.providers import backends, checks, registry  # noqa: E402
from lumen.search import images as visual  # noqa: E402
from lumen.voice.vad import SileroStream as REAL_VOICE_DETECTOR  # noqa: E402

OLD = time.mktime((2019, 6, 1, 12, 0, 0, 0, 0, -1))


def _sample_files(root: Path) -> dict[str, Path]:
    """A small, known set of files covering each kind of document Lumen reads."""
    import numpy as np
    import pymupdf
    from docx import Document
    from PIL import Image

    docs, downloads = root / "Documents", root / "Downloads"
    (docs / "old").mkdir(parents=True)
    downloads.mkdir()
    files = {
        "notes": docs / "budget-notes.txt",
        "pdf": docs / "invoice-1042.pdf",
        "docx": docs / "library-letter.docx",
        "old": docs / "old" / "annual-report.txt",
        "recipe": downloads / "lentil-soup.md",
        "image": downloads / "holiday.png",
    }
    files["notes"].write_text("Quarterly budget review: travel costs went up, printer paper went down.\n")
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Invoice 1042 for garden furniture, total 250 EUR")
    pdf.save(files["pdf"])
    letter = Document()
    letter.add_paragraph("Dear Alex, your library card renewal is due next month.")
    letter.save(files["docx"])
    files["old"].write_text("Annual report: membership grew in every region.\n")
    os.utime(files["old"], (OLD, OLD))
    files["recipe"].write_text("# Lentil soup\nOnion, carrot, red lentils, cumin.\n")
    noise = np.random.default_rng(0).integers(0, 255, (120, 160, 3), dtype=np.uint8)
    Image.fromarray(noise).save(files["image"])
    return files


class Env:
    """Paths of one test's Lumen setup."""

    def __init__(self, base: Path):
        self.base = base
        self.data = base / "data"
        self.roots = base / "roots"
        self.files: dict[str, Path] = {}
        self.app = None

    @property
    def documents(self) -> Path:
        return self.roots / "Documents"

    @property
    def downloads(self) -> Path:
        return self.roots / "Downloads"


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    """A fresh Lumen: own data folder, two indexed folders with sample files, nothing indexed yet."""
    e = Env(tmp_path)
    e.data.mkdir()
    e.files = _sample_files(e.roots)
    roots = [e.documents.resolve(), e.downloads.resolve()]

    # The indexer runs as a subprocess: it reads the environment
    for key, value in {
        "LUMEN_DATA": str(e.data),
        "LUMEN_ROOTS": ":".join(map(str, roots)),
    }.items():
        monkeypatch.setenv(key, value)

    # In-process settings
    for name, value in {
        "data_dir": e.data,
        "roots": roots,
        "paused_roots": [],
        "excluded": [],
        "power_mode": "saver",
        "captions": False,
        "media": False,
        "visual": False,
        "transcripts": False,
        "open_mode": "print",
        "write_enabled": True,
        "cpu_only": False,
        "threads": 4,
        "ollama_host": "http://127.0.0.1:9",
        "agent_provider": "ollama",
        "vision_provider": "ollama",
        "agent_model": "qwen3.5:2b",
        "caption_model": "qwen3.5:2b",
        "whisper_model": "small",
        "notes_dir": "",
        "reminder_notify": True,
        "reminder_speak": True,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "providers", registry.defaults())

    monkeypatch.setattr(visual, "_cache", {"key": None})
    e.app = create_app()  # its own services: index runner, chats, pairing
    yield e
    e.app.state.services.indexer.stop()


def index_now() -> dict:
    """Build the index in this process (the API runs it as a subprocess)."""
    return build_index()


@pytest.fixture
def indexed(env) -> Env:
    index_now()
    return env


@pytest.fixture
def local(env) -> TestClient:
    """The desktop app: requests from the laptop itself."""
    return TestClient(env.app, client=("127.0.0.1", 50000))


@pytest.fixture
def remote(env) -> TestClient:
    """A phone on the network (not the laptop)."""
    return TestClient(env.app, client=("192.168.1.50", 50000))


def wait_until(check, timeout: float = 30, step: float = 0.1):
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(step)
    return False


# ---------- a scripted chat model ----------


def tool_call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}", "type": "tool_call"}])


class ScriptedModel(BaseChatModel):
    """Answers with the next scripted message each time the agent asks; records what it was sent."""

    script: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        msg = self.script.pop(0) if self.script else AIMessage(content="(script ended)")
        if isinstance(msg, Exception):  # a scripted failure
            raise msg
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.fixture
def model(env, monkeypatch) -> ScriptedModel:
    """Replace the chat model with a scripted one: set `model.script` before chatting."""
    fake = ScriptedModel()
    monkeypatch.setattr(backends, "chat_model", lambda *a, **k: fake)
    return fake


def sse(response) -> list[dict]:
    """The JSON events of a server-sent event stream."""
    import json

    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


# ---------- hooks for tests: every reach into Lumen's internals goes through these ----------


@pytest.fixture
def set_settings(env, monkeypatch):
    """Change settings for one test, e.g. set_settings(captions=True)."""

    def apply(**values):
        for name, value in values.items():
            assert hasattr(settings, name), name
            monkeypatch.setattr(settings, name, value)

    return apply


@pytest.fixture
def ai_on(set_settings):
    """Plugged in, AI passes allowed (the default test setup is 'saver')."""
    set_settings(power_mode="performance")
    return set_settings


class FakeVision:
    """A vision model: set `.reply` (text) or `.error` (exception); counts `.calls`."""

    def __init__(self):
        self.reply = "A red sports car parked by the sea. Text: none"
        self.error: Exception | None = None
        self.calls = 0

    def __call__(self, prompt, png, *a, **k):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def vision(env, monkeypatch) -> FakeVision:
    fake = FakeVision()
    monkeypatch.setattr(backends, "describe_image", fake)
    return fake


@pytest.fixture
def speech(env, monkeypatch):
    """A speech model that 'hears' a few timestamped lines."""
    lines = [(600.0, 605.0, "We should pack the towels."), (605.65, 607.0, "What time does the last train leave?")]
    monkeypatch.setattr(speech_pass, "load_whisper", lambda: None)
    monkeypatch.setattr(speech_pass, "transcribe", lambda path: (lines, "en"))
    return lines


@pytest.fixture
def ollama_caps(env, monkeypatch):
    """What Ollama reports a model can do: call with a list, e.g. ollama_caps(["completion", "tools"])."""

    def use(caps):
        monkeypatch.setattr(checks, "ollama_caps", lambda p, m: caps)

    return use


@pytest.fixture
def fake_clip(env, monkeypatch, set_settings):
    """An image model that only knows colour: an image points at its strongest colour channel
    (grey images at none), text at the colour it names. Turns the image pass on."""
    import numpy as np

    colours = ("red", "green", "blue")

    def one_hot(i):
        v = np.zeros(512, dtype=np.float32)
        v[i] = 1.0
        return v

    def colour_of(im) -> int:
        mean = np.asarray(im.convert("RGB"), dtype=float).mean((0, 1))
        return int(np.argmax(mean)) if mean.max() - mean.min() > 40 else 20

    def embed_text(text):
        return next((one_hot(i) for i, c in enumerate(colours) if c in text), one_hot(10))

    monkeypatch.setattr(visual, "_load", lambda: {"fake": True})
    monkeypatch.setattr(visual, "embed_images", lambda images: np.stack([one_hot(colour_of(im)) for im in images]))
    monkeypatch.setattr(visual, "embed_text", embed_text)
    set_settings(visual=True, power_mode="performance")  # the image pass is skipped in saver mode


@pytest.fixture
def graded_clip(env, monkeypatch, set_settings):
    """An image model whose scores fall off smoothly: a picture points in a direction set by its
    brightness (black 0°, white 90°), so two pictures score cos(angle between them). Lets tests
    place matches at chosen scores. Turns the image pass on."""
    import numpy as np

    def embed(im):
        angle = np.asarray(im.convert("L"), dtype=float).mean() / 255 * np.pi / 2
        v = np.zeros(512, dtype=np.float32)
        v[0], v[1] = np.cos(angle), np.sin(angle)
        return v

    monkeypatch.setattr(visual, "_load", lambda: {"fake": True})
    monkeypatch.setattr(visual, "embed_images", lambda images: np.stack([embed(im) for im in images]))
    set_settings(visual=True, power_mode="performance")


class Indexer:
    """The server's index runner, as tests need to see it."""

    def __init__(self, app):
        self._runner = app.state.services.indexer

    @property
    def process(self):
        return self._runner.proc

    def pretend_running(self, monkeypatch):
        monkeypatch.setattr(type(self._runner), "running", property(lambda self: True))


@pytest.fixture
def indexer(env) -> Indexer:
    return Indexer(env.app)


@pytest.fixture
def api(env):
    """The HTTP app (for tests that need the server's start and shutdown)."""
    return env.app


def agent_tool_names() -> list[str]:
    return [t.name for t in make_tools(lambda e: None)]


OPEN_INDEX_CODE = "from lumen.storage import db; db.connect().close()"  # run in a separate process


def setting_in_fresh_python(env_vars: dict, name: str, after_start: bool = False) -> str:
    """A setting as a new process sees it (settings read the environment at start). With
    `after_start`, also after loading what was saved in the data folder, as the server and CLI do."""
    import subprocess
    import sys

    clean = {k: v for k, v in os.environ.items() if not k.startswith(("LUMEN_", "OS_OPERATOR_"))}
    load = "from lumen.core.bootstrap import load_saved_state; load_saved_state(); " if after_start else ""
    code = f"{load}from lumen.core.settings import settings; print(settings.{name})"
    out = subprocess.run(
        [sys.executable, "-c", code], env={**clean, **env_vars}, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def logs(env, tmp_path, monkeypatch) -> Path:
    """The server's log, written to this test's own folder. Returns the folder."""
    import logging

    from lumen.core import logging as lumen_logging

    folder = tmp_path / "logs"
    monkeypatch.setenv("LUMEN_LOG_DIR", str(folder))
    monkeypatch.setenv("LUMEN_LOG_LEVEL", "DEBUG")
    lumen_logging.setup("server")
    yield folder
    for h in list(logging.getLogger("lumen").handlers):
        logging.getLogger("lumen").removeHandler(h)
        h.close()


def add_route(app, path: str, fn):
    """A route for tests only (e.g. one that crashes)."""
    app.add_api_route(path, fn, methods=["GET"])


def raise_error(kind: str, message: str, hint: str = ""):
    """Raise one of Lumen's own errors (InvalidInput, NotFound, …) by name."""
    from lumen.core import errors

    raise getattr(errors, kind)(message, hint)


def index_file() -> Path:
    """Where the search index is kept (one SQLite file in the data folder)."""
    return settings.db_path


@pytest.fixture
def provider_models(env, monkeypatch):
    """Set what a provider lists as its models (no server needed)."""

    def use(models: list[dict]):
        monkeypatch.setattr(backends, "list_models", lambda pid: models)

    return use


@pytest.fixture
def text_limits(env, monkeypatch):
    """Lower how much text is read per file, so tests of big files stay small and fast."""
    from lumen.core import limits

    def use(**values: int):
        for name, value in values.items():
            monkeypatch.setattr(limits, name, value)

    return use


class FakeVoice:
    """Speech models for voice tests: 'hears' the scripted sentences in order, and speaks a
    sentence as a little silent audio (slowly with `seconds_per_sentence`, to test interrupting)."""

    sample_rate = 22050

    def __init__(self):
        self.heard: list[str] = []
        self.spoken: list[str] = []
        self.seconds_per_sentence = 0.0
        self.transcriptions = 0

    def transcribe(self, audio) -> str:
        self.transcriptions += 1
        return self.heard.pop(0) if self.heard else ""

    def speak(self, text: str):
        time.sleep(self.seconds_per_sentence)
        self.spoken.append(text)
        yield b"\x00\x00" * 2205  # 0.1 s
        yield b"\x00\x00" * 2205


class LoudnessDetector:
    """Stands in for the voice detector in tests: the test tone is speech, room noise isn't.
    (The real one, Silero, would rightly say a tone isn't a voice.)"""

    def __call__(self, window) -> float:
        import numpy as np

        return 1.0 if float(np.sqrt(np.mean(window**2))) > 0.05 else 0.0


@pytest.fixture
def voice(env, monkeypatch) -> FakeVoice:
    from lumen.voice import stt, tts, vad

    fake = FakeVoice()
    monkeypatch.setattr(stt, "load", lambda: None)
    monkeypatch.setattr(stt, "transcribe", fake.transcribe)
    monkeypatch.setattr(tts, "load", lambda: fake)
    monkeypatch.setattr(tts, "available", lambda: True)
    monkeypatch.setattr(vad, "SileroStream", LoudnessDetector)
    return fake


@pytest.fixture
def real_voice_detector(voice, monkeypatch):
    """The fake speech models, but the real voice detector (Silero ships inside faster-whisper:
    nothing to download)."""
    from lumen.voice import vad

    monkeypatch.setattr(vad, "SileroStream", REAL_VOICE_DETECTOR)
    return voice


def pcm(seconds: float, loud: bool) -> bytes:
    """Microphone audio (PCM16, 16 kHz): a voice-like tone, or quiet room noise."""
    import numpy as np

    n = int(16000 * seconds)
    if loud:
        wave = np.sin(2 * np.pi * 220 * np.arange(n) / 16000) * 0.3
    else:
        wave = np.random.default_rng(n).normal(0, 0.003, n)
    return (wave * 32767).astype("<i2").tobytes()


# ---------- notes, to-dos and reminders ----------

from lumen.agent.tools.planner import wanted as wants_planner  # noqa: E402,F401
from lumen.planner.scheduler import desktop_notify  # noqa: E402,F401
from lumen.planner.times import parse_when  # noqa: E402,F401  (tests import it from here)


class Reminders:
    """The reminder thread, run by hand: set `.now` (seconds), call `.tick()`; desktop
    notifications land in `.shown`, spoken ones in `.said`."""

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.now = time.time()
        self.shown: list[str] = []
        self.said: list[str] = []
        scheduler.now = lambda: self.now
        scheduler.notify = lambda title, body: self.shown.append(body)
        scheduler.speakers.append(self.said.append)

    def tick(self) -> list[dict]:
        return self.scheduler.tick()


@pytest.fixture
def reminders(env) -> Reminders:
    return Reminders(env.app.state.services.reminders)


@pytest.fixture
def commands(monkeypatch):
    """Commands Lumen runs (subprocess.run) are recorded instead; set `.missing` to hide programs."""

    class Ran(list):
        missing: set = set()

    ran = Ran()
    import shutil as _shutil
    import subprocess as _subprocess

    real_which = _shutil.which
    monkeypatch.setattr(
        _shutil, "which", lambda name, *a, **k: None if name in ran.missing else real_which(name) or f"/usr/bin/{name}"
    )
    monkeypatch.setattr(
        _subprocess, "run", lambda cmd, *a, **k: ran.append(cmd) or _subprocess.CompletedProcess(cmd, 0, "", "")
    )
    return ran


@pytest.fixture
def notes_folder(env) -> Path:
    """Where notes are saved by default: "Lumen Notes" in the first indexed folder."""
    return env.documents.resolve() / "Lumen Notes"
