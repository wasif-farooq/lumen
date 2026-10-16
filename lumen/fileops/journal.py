"""The log of changes made (actions.jsonl in the data folder), so they can be undone."""

import json
from pathlib import Path

from ..core.settings import settings


def log_file() -> Path:
    return settings.data_dir / "actions.jsonl"


def append(entry: dict) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with log_file().open("a") as f:
        f.write(json.dumps(entry) + "\n")


def history() -> list[dict]:
    try:
        return [json.loads(line) for line in log_file().read_text().splitlines() if line.strip()]
    except OSError:
        return []


def save(entries: list[dict]) -> None:
    log_file().write_text("".join(json.dumps(e) + "\n" for e in entries))
