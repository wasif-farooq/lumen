import os
import shutil
from pathlib import Path


def env(name: str, default: str | None = None) -> str | None:
    """LUMEN_<name>, or OS_OPERATOR_<name> from before the rename."""
    return os.environ.get(f"LUMEN_{name}", os.environ.get(f"OS_OPERATOR_{name}", default))


def _data_dir() -> Path:
    if env("DATA"):
        return Path(env("DATA")).expanduser()
    new, old = Path("~/.local/share/lumen").expanduser(), Path("~/.local/share/os-operator").expanduser()
    return old if old.is_dir() and not new.exists() else new  # keep an index made before the rename


# Folders to index; override with LUMEN_ROOTS="~/a:~/b"
ROOTS = [
    Path(p).expanduser().resolve()
    for p in env("ROOTS", "~/Documents:~/Downloads:~/Desktop").split(":")
    if p
]

PAUSED_ROOTS: list[Path] = []  # folders kept in the index but not re-scanned (set in the app)
EXCLUDED: list[str] = []  # files and folders kept out of the index (set in the app)

DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "index.db"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
AGENT_MODEL = env("MODEL", "qwen3.5:2b")
# Which provider runs each role ("ollama" or one added in the app); see providers.py
AGENT_PROVIDER = "ollama"
VISION_PROVIDER = "ollama"
PROVIDERS: dict = {}
NUM_CTX = int(env("NUM_CTX", "8192"))

# Describe images and scanned PDFs with a vision model during indexing (same model = no GPU swap)
CAPTIONS = env("CAPTIONS", "1") != "0"
CAPTION_MODEL = env("CAPTION_MODEL", AGENT_MODEL)

# Power use while indexing: auto (AI passes only on AC power) | saver | performance
POWER_MODE = env("POWER", "auto")
THREADS = int(env("THREADS", "4"))  # CPU threads for whisper/ffmpeg
INDEX_KEEP_ALIVE = "2m"

# Run every model on the CPU only: slower, but the dedicated GPU can stay asleep (saves battery)
CPU_ONLY = env("CPU_ONLY", "0") == "1"


def ollama_options(**opts) -> dict:
    """Options for every Ollama call; num_gpu=0 keeps all model layers on the CPU."""
    return {**opts, "num_gpu": 0} if CPU_ONLY else opts  # let Ollama free the GPU soon after indexing instead of holding it 30 min

# Video/audio: metadata + frame description + speech transcript (faster-whisper on CPU)
MEDIA = env("MEDIA", "1") != "0"
TRANSCRIPTS = env("TRANSCRIPTS", "1") != "0"
# Image signatures for visual search, similar images and duplicates (CLIP on CPU)
VISUAL = env("VISUAL", "1") != "0"
WHISPER_MODEL = env("WHISPER_MODEL", "small")

# File changes (create/copy/move) after approval; Docker test mode sets LUMEN_WRITE=0
WRITE_ENABLED = env("WRITE", "1") != "0"

# "xdg" opens files on the desktop; "print" only reports what would be opened
# (used inside Docker, where there is no desktop to open things on).
OPEN_MODE = env("OPEN_MODE") or ("xdg" if shutil.which("xdg-open") else "print")

SKIP_DIRS = {
    "node_modules", "__pycache__", "venv", "site-packages", "dist", "build",
    "target", "vendor", "bower_components",
}

MAX_EXTRACT_BYTES = 25 * 1024 * 1024  # don't open files bigger than this for text
MAX_CONTENT_CHARS = 200_000           # text stored per file in the index
MAX_PDF_PAGES = 100
