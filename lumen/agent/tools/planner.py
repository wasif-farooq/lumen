"""Notes, to-dos and reminders from chat and voice. The model passes the user's own words; dates
and times are worked out here (lumen.planner.times), never by the model.

Small models "help" with times anyway ("tonight" becomes "tonight at 11pm", "on Friday" gets a
weekly repeat). So a time is read from the model's words only when they are a faithful copy of
what the user said; otherwise from the user's message itself. Repeats come only from the words
("every Monday", "daily"), never from a separate argument the model fills in.
"""

import re
from datetime import datetime

from langchain_core.tools import tool

from ... import planner
from ...planner import notes
from ...planner.times import When, describe, parse_when
from .context import ToolContext

ASK_WHEN = "I couldn't tell when from “{}”. Ask the user when (e.g. “tomorrow at 5pm”, “every Monday 9am”)."
STOP = {"the", "a", "an", "my", "to", "of", "for", "and", "on", "in"}
NAMES = ("add_note", "add_todo", "show_todos", "complete_todo", "set_reminder", "cancel_reminder")

# Messages that are clearly about notes, to-dos or reminders: the model then sees only these tools
# (a small model otherwise answers "note: ..." with a file search, or "write down ..." with create_file)
INTENT = re.compile(
    r"\b(?:remind(?:er|ers|ing)? me|reminders?\b|set a reminder|to-?dos?\b|todo list|task list|"
    r"(?:make|take|add|save|write|jot) (?:a |this |that |it )?(?:note|down)\b|note(?: that| down|:)|"
    r"remember (?:that|this)\b|don'?t (?:let me )?forget|(?:to|on|onto|from) (?:my|the) [\w-]+ list\b|"
    r"what do i (?:have|need) to do|mark .{1,60}? (?:as )?(?:done|finished|complete)\b|(?:done|finished) with\b|"
    r"(?:show|see|read|open) (?:me )?(?:my|the) [\w-]+ list\b|what'?s on (?:my|the) [\w-]+ list|"
    r"cancel .{0,40}?reminder|stop reminding)",
    re.IGNORECASE,
)


def wanted(text: str) -> bool:
    """The user clearly asks about notes, to-dos or reminders."""
    return bool(INTENT.search(text))


def build(ctx: ToolContext) -> dict:
    emit, state = ctx.emit, ctx.state

    @tool
    def add_note(title: str, text: str) -> str:
        """Save a note for the user (a Markdown file in their notes folder). If a note with this
        title exists, the text is added at its end.

        Args:
            title: a short title, e.g. "Plumber", "Gift ideas".
            text: what to write down, in the user's words.
        """
        existing = notes.find(title)
        note = notes.append(existing["name"], text) if existing else notes.create(title, text)
        emit({"type": "note_saved", "name": note["name"], "title": note["title"], "added_to": bool(existing),
              "action_id": note["action_id"]})  # fmt: skip
        return f"{'Added to' if existing else 'Saved'} the note “{note['title']}”."

    @tool
    def add_todo(text: str, list: str = "", due: str = "", priority: str = "") -> str:
        """Add a NEW to-do (a task, or an item on a list such as Shopping): "add milk to my shopping
        list", "I need to call the bank". Not for showing a list (show_todos) or for something done
        (complete_todo).

        Args:
            text: the task, e.g. "buy milk", "call the bank".
            list: the list's name, e.g. "Shopping", "Work"; empty for the main to-do list. A new name makes a new list.
            due: when it is due, in the user's own words ("Friday", "tomorrow at 5pm"); empty if not said.
            priority: "high", "medium" or "low"; empty if not said.
        """
        store = planner.store()
        due_at = None
        if due.strip():
            w = _when(due, state)
            if w is None:
                return ASK_WHEN.format(due)
            due_at = w.at.timestamp()
        said = state.get("user_text", "")
        if list.strip() and said and not re.search(rf"\b{re.escape(list.strip())}\b", said, re.IGNORECASE):
            list = ""  # a list the user never mentioned (the model picked one it knows of)
        if not list.strip():  # "add milk to my shopping list" with the list left out
            list = _list_said(text, said, [x["name"] for x in store.lists()])
        text = _bare(text, list)
        todo = store.add_todo(text, store.list_named(list, create=True)["id"], priority=priority or 0, due_at=due_at)
        emit({"type": "todo_added", "todo": todo})
        when = f", due {describe(datetime.fromtimestamp(due_at), 'none', datetime.now())}" if due_at else ""
        return f"Added “{todo['text']}” to {todo['list']}{when}."

    @tool
    def show_todos(list: str = "") -> str:
        """Show the user's open to-dos (all lists, or one) and upcoming reminders: "what do I have to
        do?", "show me my shopping list", "what reminders do I have?".

        Args:
            list: a list's name to show only that list; empty for everything.
        """
        store = planner.store()
        list_id = store.list_named(list)["id"] if list.strip() else None
        todos = store.todos(list_id)
        upcoming = [] if list.strip() else store.reminders()[:10]
        state["todos"] = [t["id"] for t in todos]
        state["reminders"] = [r["id"] for r in upcoming]
        now = datetime.now()
        emit({"type": "todos", "todos": todos, "reminders": [_shown(r, now) for r in upcoming]})
        if not todos and not upcoming:
            return "Nothing to do, and no reminders."
        lines = [f"{i}. {t['text']} ({t['list']})" for i, t in enumerate(todos, 1)]
        lines += [f"Reminder {i}: {r['text']} – {_shown(r, now)['when']}" for i, r in enumerate(upcoming, 1)]
        return "\n".join(lines)

    @tool
    def complete_todo(todo: str) -> str:
        """Mark a to-do as done: "I bought the milk", "done with the electricity bill", "mark fix the
        tap as done".

        Args:
            todo: its number from the last list shown (e.g. "2"), or words from it (e.g. "milk").
        """
        store = planner.store()
        found = _pick(todo, state.get("todos", []), store.todos(), "to-do")
        if isinstance(found, str):
            return found
        done = store.update_todo(found["id"], done=True)
        emit({"type": "todo_done", "todo": done})
        return f"Done: “{done['text']}”."

    @tool
    def set_reminder(text: str, when: str) -> str:
        """Remind the user of something at a time (a notification on the laptop, and said aloud
        when voice is on).

        Args:
            text: what to remind them of, e.g. "pay the rent".
            when: the time in the user's OWN words, copied exactly as said, including "every …" for
                repeats: "in 20 minutes", "tomorrow at 5pm", "every Monday at 9". Never add a time
                or date the user didn't say.
        """
        w = _when(when, state)
        if w is None:
            return ASK_WHEN.format(when)
        repeat = w.repeat
        if repeat == "none" and w.at <= datetime.now():
            return f"{describe(w.at, 'none', datetime.now())} has already passed. Ask the user for a later time."
        r = planner.store().add_reminder(text, w.at.timestamp(), repeat)
        shown = _shown(r, datetime.now())
        emit({"type": "reminder_set", "reminder": shown})
        return f"OK: reminder “{r['text']}” {shown['when']}."

    @tool
    def cancel_reminder(reminder: str) -> str:
        """Cancel a reminder.

        Args:
            reminder: its number from the last list shown (e.g. "1"), or words from it (e.g. "rent").
        """
        store = planner.store()
        found = _pick(reminder, state.get("reminders", []), store.reminders(), "reminder")
        if isinstance(found, str):
            return found
        r = store.set_active(found["id"], False)
        emit({"type": "reminder_cancelled", "reminder": _shown(r, datetime.now())})
        return f"Cancelled the reminder “{r['text']}”."

    return {f.name: f for f in (add_note, add_todo, show_todos, complete_todo, set_reminder, cancel_reminder)}


def _bare(text: str, list_name: str) -> str:
    """The to-do itself when the model copied the whole request: "add eggs to shopping" -> "eggs"."""
    t = re.sub(r"^\s*(?:please\s+)?(?:add|put)\s+", "", text, flags=re.IGNORECASE)
    if list_name.strip():
        onto = rf"\s+(?:to|on|onto|in)\s+(?:my\s+|the\s+)?{re.escape(list_name.strip())}(?:\s+list)?\s*$"
        t = re.sub(onto, "", t, flags=re.IGNORECASE)
    return t.strip() or text


def _list_said(text: str, said: str, lists: list[str]) -> str:
    """The existing list the user put this to-do on ("milk … to my shopping list"), or ""."""
    words = [w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2]
    said = said.lower()
    for name in lists:
        onto = rf"\b(?:to|on|onto|in)\s+(?:my\s+|the\s+)?{re.escape(name.lower())}\b"
        if any(re.search(rf"\b{re.escape(w)}\b.{{0,40}}?{onto}", said) for w in words):
            return name
    return ""


def _when(words: str, state: dict) -> When | None:
    """The time the user meant: from the model's words when they only repeat what the user said,
    otherwise from the user's own message (the model added or changed something)."""
    said = state.get("user_text", "")
    now = datetime.now()
    from_user = parse_when(said, now) if said else None
    if from_user is not None and not _copied(words, said):
        return from_user
    w = parse_when(words, now)
    if w is not None and w.repeat == "none" and from_user is not None and from_user.repeat != "none":
        return from_user  # the user said "every day…" but the model put that in the text
    return w


def _copied(words: str, said: str) -> bool:
    """Every word and number of `words` is in what the user said ("at 5" ~ "at 5", not "5pm")."""
    have = set(re.findall(r"[a-z0-9]+", said.lower()))
    return all(t in have for t in re.findall(r"[a-z0-9]+", words.lower()))


def _pick(what: str, numbered: list[int], items: list[dict], kind: str) -> dict | str:
    """One item by its number in the last list shown, or by words in its text; else a question."""
    w = what.strip().lstrip("#")
    if w.isdigit():
        n = int(w)
        if not 1 <= n <= len(numbered):
            return f"There is no {kind} {n}. Call show_todos to see the numbers."
        match = [i for i in items if i["id"] == numbered[n - 1]]
        return match[0] if match else f"That {kind} is already gone."
    hits = [i for i in items if w.lower() in i["text"].lower()]
    if not hits:  # the model passed the whole sentence: an item all of whose words were said
        said = set(re.findall(r"[a-z0-9]+", w.lower()))
        hits = [i for i in items if (ws := set(re.findall(r"[a-z0-9]+", i["text"].lower())) - STOP) and ws <= said]
    if len(hits) == 1 or (hits and len({i["text"].strip().lower() for i in hits}) == 1):
        return hits[0]  # one match, or the same thing written down twice
    if not hits:
        return f"No {kind} matches “{what}”."
    names = "; ".join(f"“{i['text']}”" for i in hits[:5])
    return f"Several match “{what}”: {names}. Ask the user which one."


def _shown(r: dict, now: datetime) -> dict:
    at = r["next_at"] if r["next_at"] is not None else r["at"]
    return {**r, "when": describe(datetime.fromtimestamp(at), r["repeat"], now)}
