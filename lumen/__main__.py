"""lumen CLI.

  python -m lumen index            build / refresh the file index
  python -m lumen stats            show index size
  python -m lumen search WORDS     search directly (no AI)
  python -m lumen ask "QUESTION"   one question to the agent
  python -m lumen chat             interactive terminal chat
"""

import argparse
import json
import os
import sys

from rich.console import Console
from rich.markdown import Markdown

from .core.settings import settings
from . import index
from .search import text as text_search
from .storage import catalog

console = Console()


def _event(**kw):
    """Machine-readable progress for the app (it reads '@@{json}' lines); off on the plain CLI."""
    if os.environ.get("LUMEN_EVENTS"):
        print("@@" + json.dumps(kw, default=str), flush=True)


def cmd_index(a):
    from . import power

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

    def on_caption(n, total, path, caption):
        _event(item={"done": n, "total": total, "path": path, "note": caption[:300]})
        console.print(f"  [{n}/{total}] {path}\n      {caption[:160]}", style="dim", highlight=False, markup=False)

    def on_scan(s):
        _event(scanned=s["scanned"])
        console.print(f"  scanned {s['scanned']:,} …", style="dim")

    power.on_pause = lambda paused: _event(paused=paused)
    s = index.build_index(
        progress=on_scan,
        on_phase=lambda name: _event(phase=name),
        captions=False if a.no_captions else None,
        on_caption=on_caption,
        media=False if a.no_media else None,
        transcripts=False if a.no_transcripts else None,
    )
    _event(summary=s)
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
        console.print(f"Captions ({settings.caption_model}): {c['captioned']} described, {c['failed']} failed, {c['seconds']}s")
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
            f"with whisper-{settings.whisper_model}), {m['reused']} duplicates reused, {m['failed']} failed, {m['seconds']}s"
        )


def cmd_stats(_):
    console.print(catalog.stats())


def cmd_search(a):
    hits = text_search.search(" ".join(a.words), a.ext, a.after, a.before, a.folder, a.limit)
    for i, h in enumerate(hits, 1):
        console.print(h.line(i), highlight=False, markup=False)
    if not hits:
        console.print("No results.")


def _run_turn(session, text: str):
    from langgraph.errors import GraphRecursionError

    try:
        events = session.stream(text)
        while events is not None:
            plan = _stream_turn(events)
            events = None
            if plan:  # a change waits for approval
                console.print(f"\n[bold yellow]Approve?[/bold yellow] {plan['summary']}", highlight=False)
                if plan.get("preview"):
                    console.print(plan["preview"], style="dim", markup=False)
                answer = console.input("[bold]y[/bold]/n > ").strip().lower()
                events = session.resume(answer in ("y", "yes"))
    except GraphRecursionError:
        console.print("I went in circles on that one and stopped. Try rephrasing it more specifically.", style="yellow")


def _stream_turn(events):
    """Print one run of the agent; returns the pending approval request, if it paused on one."""
    with console.status("thinking…", spinner="dots") as status:
        for kind, payload in events:
            if kind == "approval":
                status.stop()
                return payload
            if kind == "tool_call":
                name, args = payload
                console.print(f"  → {name}({json.dumps(args, ensure_ascii=False)})", style="cyan", highlight=False, markup=False)
                status.update(f"running {name}…")
            elif kind == "tool_result":
                first = payload.splitlines()[0] if payload else ""
                console.print(f"    {first[:120]}", style="dim", highlight=False, markup=False)
                status.update("thinking…")
            elif kind == "answer":
                status.stop()
                console.print(Markdown(payload or "(no answer)"))


def _session():
    from .agent import Session

    s = Session()
    stats = catalog.stats()
    console.print(
        f"[bold]lumen[/bold] · model {settings.agent_model} · {stats['files']:,} files indexed · "
        f"{'CPU only' if settings.cpu_only else 'GPU'} · open mode: {settings.open_mode} · "
        f"langfuse: {'on' if s.tracing else 'off'}",
        style="dim",
    )
    if stats["files"] == 0:
        console.print("Index is empty, run: python -m lumen index", style="yellow")
    return s


def cmd_ask(a):
    s = _session()
    try:
        _run_turn(s, " ".join(a.question))
    finally:
        s.close()


def cmd_chat(_):
    s = _session()
    console.print("Ask me to find or open files. Type 'exit' to quit.\n", style="dim")
    try:
        while True:
            try:
                text = console.input("[bold green]you>[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"exit", "quit", "q"}:
                break
            if text:
                _run_turn(s, text)
                console.print()
    finally:
        s.close()


def cmd_serve(a):
    from .server import run

    run(lan=a.lan, port=a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="lumen")
    sub = p.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("index")
    ip.add_argument("--no-captions", action="store_true", help="skip describing images/scans")
    ip.add_argument("--no-media", action="store_true", help="skip video/audio")
    ip.add_argument("--power", choices=["auto", "saver", "performance"], help="override LUMEN_POWER")
    ip.add_argument("--no-transcripts", action="store_true", help="video/audio: skip speech-to-text")
    ip.set_defaults(fn=cmd_index)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sp = sub.add_parser("search")
    sp.add_argument("words", nargs="*")
    sp.add_argument("--ext", default="")
    sp.add_argument("--after", default="")
    sp.add_argument("--before", default="")
    sp.add_argument("--folder", default="")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=cmd_search)
    ap = sub.add_parser("ask")
    ap.add_argument("question", nargs="+")
    ap.set_defaults(fn=cmd_ask)
    sub.add_parser("chat").set_defaults(fn=cmd_chat)
    sv = sub.add_parser("serve", help="API server for the desktop/mobile app")
    sv.add_argument("--lan", action="store_true", help="also accept paired phones on the local network")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    from .core.bootstrap import load_saved_state

    load_saved_state()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
