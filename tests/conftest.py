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

from lumen import config, index, providers, server, visual  # noqa: E402

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
        "DATA_DIR": e.data, "DB_PATH": e.data / "index.db", "ROOTS": roots, "PAUSED_ROOTS": [],
        "EXCLUDED": [], "POWER_MODE": "saver", "CAPTIONS": False, "MEDIA": False, "VISUAL": False,
        "TRANSCRIPTS": False, "OPEN_MODE": "print", "WRITE_ENABLED": True, "CPU_ONLY": False,
        "OLLAMA_HOST": "http://127.0.0.1:9", "AGENT_PROVIDER": "ollama", "VISION_PROVIDER": "ollama",
        "AGENT_MODEL": "qwen3.5:2b", "CAPTION_MODEL": "qwen3.5:2b", "WHISPER_MODEL": "small",
    }.items():
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(config, "PROVIDERS", providers._defaults())

    # Server state lives in module globals today: start each test from scratch
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "_chat_db", None)
    monkeypatch.setattr(server, "_saver", None)
    monkeypatch.setattr(server, "_state", {"lan": False})
    monkeypatch.setattr(server, "_pair", {"code": None, "expires": 0.0, "tries": 0})
    monkeypatch.setattr(server, "_indexer", server.Indexer())
    monkeypatch.setattr(visual, "_cache", {"key": None})
    yield e
    server._indexer.stop()


def index_now() -> dict:
    """Build the index in this process (the API runs it as a subprocess)."""
    return index.build_index()


@pytest.fixture
def indexed(env) -> Env:
    index_now()
    return env


@pytest.fixture
def local(env) -> TestClient:
    """The desktop app: requests from the laptop itself."""
    return TestClient(server.app, client=("127.0.0.1", 50000))


@pytest.fixture
def remote(env) -> TestClient:
    """A phone on the network (not the laptop)."""
    return TestClient(server.app, client=("192.168.1.50", 50000))


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
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.fixture
def model(env, monkeypatch) -> ScriptedModel:
    """Replace the chat model with a scripted one: set `model.script` before chatting."""
    fake = ScriptedModel()
    monkeypatch.setattr(providers, "chat_model", lambda *a, **k: fake)
    return fake


def sse(response) -> list[dict]:
    """The JSON events of a server-sent event stream."""
    import json

    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
