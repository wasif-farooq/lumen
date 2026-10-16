"""User settings saved in the data folder and applied on top of the environment defaults."""

import json
from pathlib import Path

from . import config

FIELDS = {
    "power_mode": ("POWER_MODE", str),
    "cpu_only": ("CPU_ONLY", bool),
    "threads": ("THREADS", int),
    "captions": ("CAPTIONS", bool),
    "media": ("MEDIA", bool),
    "transcripts": ("TRANSCRIPTS", bool),
    "visual": ("VISUAL", bool),
}


def _file() -> Path:
    return config.DATA_DIR / "settings.json"


def current() -> dict:
    out = {name: getattr(config, attr) for name, (attr, _) in FIELDS.items()}
    out["roots"] = [str(r) for r in config.ROOTS]
    out["paused_roots"] = [str(r) for r in config.PAUSED_ROOTS]
    out["excluded"] = list(config.EXCLUDED)
    return out


def load():
    """Apply saved settings (called once at server start)."""
    from . import providers

    providers.load()
    try:
        saved = json.loads(_file().read_text())
    except (OSError, ValueError):
        return
    try:
        _apply(saved)
    except ValueError:
        # A saved folder is gone (or not mounted, e.g. in Docker): keep the default folders
        _apply({k: v for k, v in saved.items() if k != "roots"})


def update(changes: dict) -> dict:
    _apply(changes)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(current(), indent=1))
    return current()


def _apply(values: dict):
    for name, (attr, typ) in FIELDS.items():
        if name in values and values[name] is not None:
            setattr(config, attr, typ(values[name]))
    if config.POWER_MODE not in ("auto", "saver", "performance"):
        config.POWER_MODE = "auto"
    config.THREADS = max(1, min(config.THREADS, 32))
    if "roots" in values and values["roots"]:
        config.ROOTS = check_roots(values["roots"])
    if "paused_roots" in values:
        config.PAUSED_ROOTS = [Path(p).expanduser().resolve() for p in values["paused_roots"] or []]
    if "excluded" in values:
        config.EXCLUDED = sorted({str(Path(p).expanduser().resolve()) for p in values["excluded"] or []})
    config.PAUSED_ROOTS = [r for r in config.PAUSED_ROOTS if r in config.ROOTS]  # drop folders no longer indexed


def check_roots(paths: list[str]) -> list[Path]:
    """Validate folders to index; raises ValueError with a message for the user."""
    roots: list[Path] = []
    for raw in paths:
        r = Path(raw).expanduser().resolve()
        if not r.exists():
            # Common in Docker: the folder exists on the laptop but is not mounted into the container
            raise ValueError(f"The server can't see {r}. If it runs in Docker, mount that folder into the container.")
        if not r.is_dir():
            raise ValueError(f"Not a folder: {r}")
        if r == Path("/") or r == Path.home().parent:
            raise ValueError(f"Too broad to index: {r}")
        # Skip duplicates and folders already covered by another one
        if any(r == o or r.is_relative_to(o) for o in roots):
            continue
        roots = [o for o in roots if not o.is_relative_to(r)] + [r]
    if not roots:
        raise ValueError("Keep at least one folder")
    return roots
