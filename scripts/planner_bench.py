# ruff: noqa: E501  (the table of phrases reads best one per line)
"""Does the chat model pick the right tool for notes, to-dos and reminders, and pass the user's own
words? The real agent and model (Ollama) on a throwaway data folder; nothing of yours is touched.

    uv run python scripts/planner_bench.py [--model qwen3.5:2b] [--only reminder,todo]

Each phrase is one fresh chat. A case passes when the expected tool was called and
what was actually saved (the reminder's time and repeat, the to-do's list, the note's text...).
Phrases about files must NOT reach the planner tools (to catch confusion with search).
"""

import argparse
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

# What must have been saved: checked against the store after each chat (set in main)
Check = Callable[["Saved"], bool]


class Saved:
    """What the chat saved: the newest reminder and to-do, notes, done and cancelled ones."""

    def __init__(self, store, notes_text: str, now) -> None:
        self.reminders = store.reminders(None)
        self.todos = store.todos(done=None)
        self.notes_text = notes_text.lower()
        self.now = now


def reminder(text: str, ref: str) -> Check:
    """The newest reminder is about `text`, at the time and repeat `ref` means."""

    def check(s: Saved) -> bool:
        from lumen.planner.times import parse_when

        if not s.reminders:
            return False
        r = max(s.reminders, key=lambda x: x["id"])
        want = parse_when(ref, s.now)
        return (
            text in r["text"].lower()
            and want is not None
            and abs(r["at"] - want.at.timestamp()) < 120
            and r["repeat"] == want.repeat
        )

    return check


def todo(text: str, list_name: str = "To-do", due_ref: str = "", priority: int | None = None) -> Check:
    def check(s: Saved) -> bool:
        from lumen.planner.times import parse_when

        t = max(s.todos, key=lambda x: x["id"])
        ok = text in t["text"].lower() and t["list"].lower() == list_name.lower()
        if due_ref:
            want = parse_when(due_ref, s.now)
            ok = ok and want is not None and t["due_at"] is not None and abs(t["due_at"] - want.at.timestamp()) < 120
        return ok and (priority is None or t["priority"] == priority)

    return check


def note(*words: str) -> Check:
    return lambda s: all(w.lower() in s.notes_text for w in words)


def done(text: str) -> Check:
    return lambda s: any(text in t["text"].lower() and t["done_at"] for t in s.todos)


def cancelled(text: str) -> Check:
    return lambda s: any(text in r["text"].lower() and not r["active"] for r in s.reminders)


def shown() -> Check:
    return lambda s: True  # the tool choice is the test


# (kind, phrase, expected first tool, what must be saved)
CASES: list[tuple[str, str, str, Check]] = [
    ("reminder", "Remind me tomorrow at 5pm to call the dentist.", "set_reminder", reminder("dentist", "tomorrow at 5pm")),
    ("reminder", "remind me in 20 minutes to take the pizza out", "set_reminder", reminder("pizza", "in 20 minutes")),
    ("reminder", "Remind me every Monday at 9 to pay the rent", "set_reminder", reminder("rent", "every Monday at 9")),
    ("reminder", "set a reminder for my mum's birthday on 3 November", "set_reminder", reminder("birthday", "3 November")),
    ("reminder", "can you remind me to drink water every day at 11am", "set_reminder", reminder("water", "every day at 11am")),
    ("reminder", "remind me tonight to lock the car", "set_reminder", reminder("car", "tonight")),
    ("reminder", "Remind me on Friday to send the report", "set_reminder", reminder("report", "Friday")),
    ("reminder", "in two hours remind me to check the oven", "set_reminder", reminder("oven", "in two hours")),
    ("todo", "Add milk to my shopping list", "add_todo", todo("milk", "Shopping")),
    ("todo", "add eggs to shopping", "add_todo", todo("eggs", "Shopping")),
    ("todo", "I need to renew my car insurance", "add_todo", todo("insurance")),
    ("todo", "put 'fix the tap' on my to-do list", "add_todo", todo("tap")),
    ("todo", "Add a task: prepare slides for Monday's meeting", "add_todo", todo("slides")),
    ("todo", "add call the bank to my work list, it's urgent", "add_todo", todo("bank", "Work", priority=3)),
    ("todo", "new todo pay the electricity bill by Friday", "add_todo", todo("electricity", due_ref="Friday")),
    ("note", "Note: the plumber is Ahmed, his number is 0300 1234567", "add_note", note("0300 1234567")),
    ("note", "write down that the wifi password is sunflower42", "add_note", note("sunflower42")),
    ("note", "remember that Sara's shoe size is 38", "add_note", note("38")),
    ("note", "make a note: ideas for the trip - Hunza, Skardu, Fairy Meadows", "add_note", note("hunza", "skardu")),
    ("note", "save a note called Recipes with: lentil soup needs cumin", "add_note", note("cumin")),
    ("show", "What do I have to do?", "show_todos", shown()),
    ("show", "show me my shopping list", "show_todos", shown()),
    ("show", "what reminders do I have", "show_todos", shown()),
    ("done", "I bought the milk", "complete_todo", done("milk")),
    ("done", "mark fix the tap as done", "complete_todo", done("tap")),
    ("done", "done with the electricity bill", "complete_todo", done("electricity")),
    ("cancel", "cancel my gym reminder", "cancel_reminder", cancelled("gym")),
    ("cancel", "stop reminding me about the plants", "cancel_reminder", cancelled("plant")),
    ("files", "where is my invoice for the garden furniture?", "*not planner*", shown()),
    ("files", "find my notes about the budget review", "*not planner*", shown()),
    ("files", "what does the library letter say?", "*not planner*", shown()),
    ("files", "open the lentil soup recipe", "*not planner*", shown()),
    ("files", "show me pictures from the holiday", "*not planner*", shown()),
    ("files", "make a folder called Taxes in Documents", "*not planner*", shown()),
]  # fmt: skip
PLANNER = {"add_note", "add_todo", "show_todos", "complete_todo", "set_reminder", "cancel_reminder"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:2b")
    ap.add_argument("--only", default="", help="kinds, e.g. reminder,todo")
    args = ap.parse_args()
    only = {k for k in args.only.split(",") if k}

    root = Path(tempfile.mkdtemp(prefix="lumen-planner-bench-"))
    docs = root / "Documents"
    docs.mkdir()
    (docs / "invoice-1042.txt").write_text("Invoice 1042 for garden furniture, total 250 EUR.\n")
    (docs / "budget-notes.txt").write_text("Quarterly budget review: travel costs went up.\n")
    (docs / "library-letter.txt").write_text("Dear Alex, your library card renewal is due next month.\n")
    (docs / "lentil-soup.md").write_text("# Lentil soup\nOnion, carrot, red lentils, cumin.\n")
    os.environ.update(
        LUMEN_DATA=str(root / "data"), LUMEN_ROOTS=str(docs), LUMEN_POWER="saver", LUMEN_LOG_DIR=str(root / "logs"),
        LUMEN_MODEL=args.model, LUMEN_OPEN_MODE="print",
    )  # fmt: skip
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        os.environ.pop(key, None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from lumen import planner
    from lumen.agent.session import Session
    from lumen.indexing.pipeline import build_index

    build_index()
    store = planner.store()  # what complete/cancel act on
    shopping = store.list_named("Shopping", create=True)["id"]
    store.add_todo("milk", shopping)
    store.add_todo("fix the tap", store.list_named("")["id"])
    store.add_todo("pay the electricity bill", store.list_named("")["id"])
    store.add_reminder("gym", time.time() + 86400, "daily")
    store.add_reminder("water the plants", time.time() + 3 * 86400, "weekly")

    from datetime import datetime

    from lumen.planner import notes

    results = []
    for kind, phrase, want, check in CASES:
        if only and kind not in only:
            continue
        t = time.perf_counter()
        now = datetime.now()
        try:
            calls = [p for k, p in Session(app=True).stream(phrase) if k == "tool_call"]
            error = ""
        except Exception as e:  # e.g. the model looping until the recursion limit
            calls, error = [], f" ({type(e).__name__})"
        seconds = time.perf_counter() - t
        name, got = calls[0] if calls else ("(none)", {})
        if want == "*not planner*":
            ok, why = not any(c[0] in PLANNER for c in calls) and not error, error
        else:
            text = " ".join(notes.get(n["name"])["text"] for n in notes.list_notes())
            called = want in [c[0] for c in calls]  # e.g. show_todos first for the numbers, then cancel_reminder
            saved_ok = called and check(Saved(store, text, now))
            ok, why = saved_ok, error or ("" if not called or saved_ok else " (saved wrong)")
        results.append((kind, ok, seconds))
        print(
            f"[{'PASS' if ok else 'FAIL'}] {kind:8s} {seconds:4.1f}s  {phrase[:52]:52s} -> {name} {got}{why}",
            flush=True,
        )

    n = len(results)
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{args.model}: {passed}/{n} right tool and words ({100 * passed / n:.0f}%), "
          f"median {sorted(s for *_, s in results)[n // 2]:.1f}s per message")  # fmt: skip
    for kind in dict.fromkeys(k for k, *_ in results):
        rs = [ok for k, ok, _ in results if k == kind]
        print(f"  {kind:8s} {sum(rs)}/{len(rs)}")


if __name__ == "__main__":
    main()
