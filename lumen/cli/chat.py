"""`lumen ask` and `lumen chat`: talk to the agent in the terminal, approving changes as they come."""

import json

from rich.markdown import Markdown

from ..core.settings import settings
from ..storage import catalog
from .console import console


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
    from ..agent import Session

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


def ask(a):
    s = _session()
    try:
        _run_turn(s, " ".join(a.question))
    finally:
        s.close()


def chat(_):
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
