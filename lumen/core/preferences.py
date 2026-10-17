"""What the user changes in the app (folders, power, what gets indexed), saved in the data folder
as settings.json and applied on top of the environment defaults."""

import json
from pathlib import Path

from .settings import settings

# Saved by name; the type turns JSON values back into settings values
FIELDS = {
    "notes_dir": str,
    "reminder_notify": bool,
    "reminder_speak": bool,
    "voice_stt_model": str,
    "voice_tts_voice": str,
    "gitignore": bool,
    "power_mode": str,
    "cpu_only": bool,
    "threads": int,
    "captions": bool,
    "media": bool,
    "transcripts": bool,
    "visual": bool,
}


def _file() -> Path:
    return settings.data_dir / "settings.json"


def current() -> dict:
    out = {name: getattr(settings, name) for name in FIELDS}
    out["roots"] = [str(r) for r in settings.roots]
    out["paused_roots"] = [str(r) for r in settings.paused_roots]
    out["excluded"] = list(settings.excluded)
    from ..planner.notes import folder  # (planner imports settings)

    out["notes_folder"] = str(folder())
    return out


def load() -> None:
    """Apply saved preferences (once, at start)."""
    try:
        saved = json.loads(_file().read_text())
    except (OSError, ValueError):
        return
    try:
        _apply(saved, strict=False)
    except ValueError:
        # A saved folder is gone (or not mounted, e.g. in Docker): keep the default folders
        _apply({k: v for k, v in saved.items() if k != "roots"}, strict=False)


def update(changes: dict) -> dict:
    _apply(changes)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(current(), indent=1))
    return current()


def _apply(values: dict, strict: bool = True) -> None:
    changes = {name: typ(values[name]) for name, typ in FIELDS.items() if values.get(name) is not None}
    if "roots" in values and values["roots"]:
        changes["roots"] = check_roots(values["roots"])
    if "paused_roots" in values:
        changes["paused_roots"] = [Path(p).expanduser().resolve() for p in values["paused_roots"] or []]
    if "excluded" in values:
        changes["excluded"] = sorted({str(Path(p).expanduser().resolve()) for p in values["excluded"] or []})
    if changes.get("notes_dir"):
        try:
            roots = changes.get("roots") or settings.roots
            changes["notes_dir"] = str(check_notes_dir(str(changes["notes_dir"]), roots))  # type: ignore[arg-type]
        except ValueError:
            if strict:
                raise
            changes.pop("notes_dir")  # at start: the default notes folder rather than none
    settings.update(**changes)


def check_notes_dir(path: str, roots: list[Path]) -> Path:
    """The notes folder must be inside an indexed folder, so search finds the notes."""
    p = Path(path).expanduser().resolve()
    if not any(p == r or p.is_relative_to(r) for r in roots):
        raise ValueError(f"Put the notes folder inside one of your indexed folders, so search finds the notes: {p}")
    return p


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
