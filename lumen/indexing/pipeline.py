"""An index run (Pipeline): scan the folders, run the AI passes when the power mode allows, then
make passages of any new text. Unchanged files are skipped, so running again only does new work."""

import json
import logging
import sqlite3
import time
from contextlib import nullcontext
from pathlib import Path

from ..core.settings import settings
from ..providers import registry
from ..search import passages
from ..storage.db import connect
from . import power
from .passes.base import Captions, IndexPass, Media, Visual
from .progress import Progress
from .scan import scan

log = logging.getLogger(__name__)


def build_index(
    roots: list[Path] | None = None,
    progress: Progress | None = None,
    captions: bool | None = None,
    media: bool | None = None,
    transcripts: bool | None = None,
) -> dict:
    """Index the folders and return the run's summary. `captions`, `media` and `transcripts`
    override the settings for this run (None: use the settings)."""
    progress = progress or Progress()
    log.info("index run: %s", ", ".join(map(str, roots or settings.roots)))
    power.on_pause = progress.paused
    power.low_priority()
    passes = [Captions(captions), Visual(), Media(media, transcripts)]
    conn = connect()
    try:
        progress.phase("scan")
        stats = scan(conn, roots or settings.roots, progress)
        _ai_passes(conn, passes, progress, stats)
        # Passages for anything with new content: documents, and descriptions/transcripts added above
        progress.phase("passages")
        stats["passages_added"] = passages.backfill(conn)
        conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
        conn.commit()
    finally:
        conn.close()
    log.info("index run done: %s", {k: v for k, v in stats.items() if not isinstance(v, dict)})
    (settings.data_dir / "last_index.json").write_text(json.dumps({"at": time.time(), "stats": stats}))
    return stats


def _ai_passes(conn: sqlite3.Connection, passes: list[IndexPass], progress: Progress, stats: dict) -> None:
    # The vision model (GPU) and whisper (CPU) are the expensive part: skipped on battery in auto mode
    allowed, why = power.heavy_allowed()
    if not allowed:
        stats["heavy_skipped"] = why
        log.info("AI passes skipped: %s", why)
        return
    # Unloading the model after indexing only means something for a local Ollama model
    with power.GpuModel(settings.caption_model) if registry.is_ollama("vision") else nullcontext():
        for p in passes:
            if p.wanted():
                progress.phase(p.name)
                stats[p.name] = p.run(conn, progress)
