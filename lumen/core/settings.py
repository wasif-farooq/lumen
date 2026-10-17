"""Lumen's settings: one object, read from the environment once and changed only through `update()`.

Defaults come from `LUMEN_*` environment variables (the `OS_OPERATOR_*` names from before the
rename still work). What the user changes in the app is saved by `lumen.core.preferences` and the
model choices by `lumen.providers`; both apply their changes to this object.
"""

import os
import shutil
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import overload

POWER_MODES = ("auto", "saver", "performance")


@overload
def env(name: str) -> str | None: ...
@overload
def env(name: str, default: str) -> str: ...
def env(name: str, default: str | None = None) -> str | None:
    """LUMEN_<name>, or OS_OPERATOR_<name> from before the rename."""
    return os.environ.get(f"LUMEN_{name}", os.environ.get(f"OS_OPERATOR_{name}", default))


def _flag(name: str, default: bool) -> bool:
    return env(name, "1" if default else "0") != "0"


def default_data_dir() -> Path:
    if data := env("DATA"):
        return Path(data).expanduser()
    new, old = Path("~/.local/share/lumen").expanduser(), Path("~/.local/share/os-operator").expanduser()
    return old if old.is_dir() and not new.exists() else new  # keep an index made before the rename


def _default_roots() -> list[Path]:
    return [Path(p).expanduser().resolve() for p in env("ROOTS", "~/Documents:~/Downloads:~/Desktop").split(":") if p]


@dataclass
class Settings:
    # Where things are
    data_dir: Path = field(default_factory=default_data_dir)
    roots: list[Path] = field(default_factory=_default_roots)  # folders to index
    paused_roots: list[Path] = field(default_factory=list)  # kept in the index, not re-scanned
    excluded: list[str] = field(default_factory=list)  # files and folders kept out of the index

    # Models (the provider of each job is chosen in the app; see lumen.providers)
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    agent_provider: str = "ollama"
    agent_model: str = field(default_factory=lambda: env("MODEL", "qwen3.5:2b"))
    vision_provider: str = "ollama"
    caption_model: str = ""  # empty: same as the chat model (no GPU swap)
    whisper_model: str = field(default_factory=lambda: env("WHISPER_MODEL", "small"))
    # Voice chat: a fast speech model (the one above transcribes videos while indexing) and a voice
    voice_stt_model: str = field(default_factory=lambda: env("VOICE_STT_MODEL", "tiny"))
    voice_tts_voice: str = field(default_factory=lambda: env("VOICE", "en_US-lessac-medium"))
    providers: dict = field(default_factory=dict)
    num_ctx: int = field(default_factory=lambda: int(env("NUM_CTX", "8192")))

    # What indexing does
    captions: bool = field(default_factory=lambda: _flag("CAPTIONS", True))  # describe images and scans
    media: bool = field(default_factory=lambda: _flag("MEDIA", True))  # describe video/audio
    transcripts: bool = field(default_factory=lambda: _flag("TRANSCRIPTS", True))
    visual: bool = field(default_factory=lambda: _flag("VISUAL", True))  # image signatures (CLIP)
    gitignore: bool = field(default_factory=lambda: _flag("GITIGNORE", True))  # skip what .gitignore files leave out

    # Power: auto (AI passes only on AC power) | saver | performance
    power_mode: str = field(default_factory=lambda: env("POWER", "auto"))
    threads: int = field(default_factory=lambda: int(env("THREADS", "4")))
    cpu_only: bool = field(default_factory=lambda: _flag("CPU_ONLY", False))  # keep the GPU asleep

    # File changes after approval; Docker test mode sets LUMEN_WRITE=0
    write_enabled: bool = field(default_factory=lambda: _flag("WRITE", True))
    # "xdg" opens files on the desktop; "print" only reports (Docker has no desktop)
    open_mode: str = field(default_factory=lambda: env("OPEN_MODE") or ("xdg" if shutil.which("xdg-open") else "print"))

    def __post_init__(self) -> None:
        self.caption_model = self.caption_model or env("CAPTION_MODEL", self.agent_model)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "index.db"

    def ollama_options(self, **opts: object) -> dict:
        """Options for every Ollama call; num_gpu=0 keeps all model layers on the CPU."""
        return {**opts, "num_gpu": 0} if self.cpu_only else opts

    def update(self, **changes: object) -> None:
        """Change settings by name, keeping values valid."""
        unknown = set(changes) - {f.name for f in fields(self)}
        if unknown:
            raise AttributeError(f"Unknown settings: {', '.join(sorted(unknown))}")
        for name, value in changes.items():
            setattr(self, name, value)
        if self.power_mode not in POWER_MODES:
            self.power_mode = "auto"
        self.threads = max(1, min(int(self.threads), 32))
        self.paused_roots = [r for r in self.paused_roots if r in self.roots]  # only indexed folders can be paused


settings = Settings()
