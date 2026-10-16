"""`lumen index`: build or refresh the index."""

import os

from ..core.settings import settings
from ..indexing.progress import EventStream, Progress, Several
from .console import console


class ConsoleProgress(Progress):
    """An index run as people read it in the terminal."""

    def scanned(self, count):
        console.print(f"  scanned {count:,} …", style="dim")

    def item(self, done, total, path, note):
        console.print(f"  [{done}/{total}] {path}\n      {note[:160]}", style="dim", highlight=False, markup=False)


def run(a):
    from ..indexing import power
    from ..indexing.pipeline import build_index

    if a.power:
        settings.update(power_mode=a.power)  # this run only, not saved
    pct = power.battery_percent()
    console.print(f"Indexing: {', '.join(map(str, settings.roots))}")
    console.print(
        f"Power: mode {settings.power_mode}, {'CPU only' if settings.cpu_only else 'GPU'}, "
        f"{'plugged in' if power.on_ac() else 'on battery'}"
        f"{f' ({pct}%)' if pct is not None else ''}, {power.threads()} threads, low priority",
        style="dim",
    )

    # Started by the server: also report machine-readable progress for the app
    progress = Several(ConsoleProgress(), EventStream()) if os.environ.get("LUMEN_EVENTS") else ConsoleProgress()
    s = build_index(
        progress=progress,
        captions=False if a.no_captions else None,
        media=False if a.no_media else None,
        transcripts=False if a.no_transcripts else None,
    )
    progress.summary(s)
    console.print(
        f"Files done in {s['seconds']}s: scanned {s['scanned']:,}, added {s['added']:,}, "
        f"updated {s['updated']:,}, removed {s['removed']:,}, text extracted from {s['with_text']:,}"
    )
    if s.get("heavy_skipped"):
        console.print(f"Skipped images/video/speech: {s['heavy_skipped']}", style="yellow")
    for part in ("captions", "media"):
        if (s.get(part) or {}).get("stopped"):
            console.print(f"{part}: {s[part]['stopped']}", style="yellow")
    c = s.get("captions")
    if c and "error" in c:
        console.print(c["error"], style="yellow")
    elif c:
        console.print(
            f"Captions ({settings.caption_model}): {c['captioned']} described, {c['failed']} failed, {c['seconds']}s"
        )
    v = s.get("visual")
    if v and "error" in v:
        console.print(v["error"], style="yellow")
    elif v:
        console.print(f"Image signatures: {v['images']} added, {v['failed']} failed, {v['seconds']}s")
    m = s.get("media")
    if m and "error" in m:
        console.print(m["error"], style="yellow")
    elif m:
        console.print(
            f"Video/audio: {m['media']} indexed ({m['described']} described, {m['transcribed']} transcribed "
            f"with whisper-{settings.whisper_model}), {m['reused']} duplicates reused, {m['failed']} failed, "
            f"{m['seconds']}s"
        )
