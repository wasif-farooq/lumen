"""Notes, to-dos and reminders: plain-words times, the API, and reminders going off."""

import time
from datetime import datetime

import pytest
from conftest import parse_when

SAT = datetime(2026, 10, 17, 14, 30)  # a Saturday afternoon


# ---------- times ----------


@pytest.mark.parametrize(
    ("words", "at", "repeat"),
    [
        ("in 2 hours", "2026-10-17 16:30", "none"),
        ("in a few minutes", "2026-10-17 14:33", "none"),
        ("in half an hour", "2026-10-17 15:00", "none"),
        ("in 3 days at 9", "2026-10-20 09:00", "none"),
        ("tomorrow at 5pm", "2026-10-18 17:00", "none"),
        ("tomorrow", "2026-10-18 09:00", "none"),
        ("at 5", "2026-10-17 17:00", "none"),  # 1-7 without am/pm: afternoon
        ("9am", "2026-10-18 09:00", "none"),  # passed today: tomorrow
        ("17:45", "2026-10-17 17:45", "none"),
        ("tonight", "2026-10-17 20:00", "none"),
        ("this evening", "2026-10-17 18:00", "none"),
        ("at 6 in the morning", "2026-10-18 06:00", "none"),
        ("Monday at 9", "2026-10-19 09:00", "none"),  # not September (the hour is not a month)
        ("next Friday 10:30am", "2026-10-23 10:30", "none"),
        ("on the 1st", "2026-11-01 09:00", "none"),
        ("on 3 November at 10", "2026-11-03 10:00", "none"),
        ("November 3rd at 10am", "2026-11-03 10:00", "none"),
        ("2026-12-24 18:00", "2026-12-24 18:00", "none"),
        ("every Monday 9am", "2026-10-19 09:00", "weekly"),
        ("every day at 8", "2026-10-18 08:00", "daily"),
        ("every weekday at 7am", "2026-10-19 07:00", "weekdays"),  # Saturday: Monday is the first
        ("every month on the 1st", "2026-11-01 09:00", "monthly"),
    ],
)
def test_plain_words_become_times(words, at, repeat):
    w = parse_when(words, SAT)
    assert w is not None, words
    assert (w.at.strftime("%Y-%m-%d %H:%M"), w.repeat) == (at, repeat)


@pytest.mark.parametrize("words", ["blah", "remind me to buy milk", "whenever", ""])
def test_words_without_a_time_are_not_guessed(words):
    assert parse_when(words, SAT) is None


def test_a_weekly_reminder_on_its_own_day_starts_today_when_the_time_is_ahead():
    monday_morning = datetime(2026, 10, 19, 8, 0)
    assert parse_when("every Monday at 9am", monday_morning).at == datetime(2026, 10, 19, 9, 0)
    assert parse_when("every Monday at 7am", monday_morning).at == datetime(2026, 10, 26, 7, 0)


# ---------- notes ----------


def test_a_note_is_a_markdown_file_in_the_notes_folder(local, notes_folder):
    r = local.post("/api/notes", json={"title": "Plumber", "text": "Ahmed, 0300 1234567", "tags": ["home"]})
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["name"] == "Plumber.md"
    raw = (notes_folder / "Plumber.md").read_text()
    assert raw.startswith("---\ntitle: Plumber\n") and "tags: home" in raw and raw.rstrip().endswith("0300 1234567")
    [listed] = local.get("/api/notes").json()
    assert listed["title"] == "Plumber" and "0300" in listed["preview"]
    assert local.get("/api/notes", params={"q": "ahmed"}).json()[0]["name"] == "Plumber.md"
    assert local.get("/api/notes", params={"q": "nothing like it"}).json() == []


def test_notes_never_overwrite_each_other(local, notes_folder):
    local.post("/api/notes", json={"title": "Ideas", "text": "one"})
    second = local.post("/api/notes", json={"title": "Ideas", "text": "two"}).json()
    assert second["name"] == "Ideas (2).md"
    assert "one" in (notes_folder / "Ideas.md").read_text()


def test_editing_and_renaming_a_note_can_be_undone(local, notes_folder):
    local.post("/api/notes", json={"title": "Shopping", "text": "milk"})
    changed = local.put("/api/notes/Shopping.md", json={"title": "Groceries", "text": "milk\neggs"}).json()
    assert changed["name"] == "Groceries.md" and not (notes_folder / "Shopping.md").exists()
    assert "eggs" in (notes_folder / "Groceries.md").read_text()
    r = local.post(f"/api/actions/{changed['action_id']}/undo", json={})
    assert r.status_code == 200, r.text
    assert (notes_folder / "Shopping.md").exists() and not (notes_folder / "Groceries.md").exists()
    assert "eggs" not in (notes_folder / "Shopping.md").read_text()


def test_a_deleted_note_goes_to_the_trash_and_undo_brings_it_back(local, notes_folder):
    local.post("/api/notes", json={"title": "Old idea", "text": "keep me"})
    gone = local.delete("/api/notes/Old idea.md").json()
    assert not (notes_folder / "Old idea.md").exists()
    local.post(f"/api/actions/{gone['action_id']}/undo", json={})
    assert "keep me" in (notes_folder / "Old idea.md").read_text()


def test_a_new_note_can_be_undone(local, notes_folder):
    note = local.post("/api/notes", json={"title": "Oops", "text": "x"}).json()
    local.post(f"/api/actions/{note['action_id']}/undo", json={})
    assert not (notes_folder / "Oops.md").exists()


def test_notes_written_by_hand_are_read_too(local, notes_folder):
    notes_folder.mkdir(parents=True)
    (notes_folder / "trip.md").write_text("# Hunza trip\nPack warm clothes.\n")
    note = local.get("/api/notes/trip.md").json()
    assert note["title"] == "Hunza trip" and "warm clothes" in note["text"]


def test_only_notes_in_the_notes_folder(local, env):
    assert local.get("/api/notes/../budget-notes.txt").status_code in (400, 404)
    assert local.get("/api/notes/missing.md").status_code == 404
    assert local.post("/api/notes", json={"title": "   ", "text": "x"}).status_code == 400


def test_test_mode_saves_no_notes(local, set_settings, notes_folder):
    set_settings(write_enabled=False)
    r = local.post("/api/notes", json={"title": "Nope", "text": "x"})
    assert r.status_code == 400 and "Test mode" in r.json()["error"]["message"]
    assert not notes_folder.exists()


def test_the_notes_folder_must_be_inside_an_indexed_folder(local, env, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    r = local.put("/api/settings", json={"notes_dir": str(outside)})
    assert r.status_code == 400 and "indexed folders" in r.json()["error"]["message"]
    inside = env.downloads / "My notes"
    inside.mkdir()
    assert local.put("/api/settings", json={"notes_dir": str(inside)}).json()["notes_folder"] == str(inside.resolve())
    local.post("/api/notes", json={"title": "Here", "text": "x"})
    assert (inside / "Here.md").exists()


# ---------- lists and to-dos ----------


def test_to_dos_in_lists(local):
    [default] = local.get("/api/lists").json()
    assert default["name"] == "To-do"
    milk = local.post("/api/todos", json={"text": "milk", "list": "Shopping", "priority": "high"}).json()
    assert milk["list"] == "Shopping" and milk["priority"] == 3
    local.post("/api/todos", json={"text": "eggs", "list": "shopping"})  # same list, any case
    assert [t["text"] for t in local.get("/api/todos").json()] == ["milk", "eggs"]
    shopping = next(x for x in local.get("/api/lists").json() if x["name"] == "Shopping")
    assert shopping["open"] == 2

    local.patch(f"/api/todos/{milk['id']}", json={"done": True})
    assert [t["text"] for t in local.get("/api/todos").json()] == ["eggs"]
    assert [t["text"] for t in local.get("/api/todos", params={"done": True}).json()] == ["milk"]
    local.patch(f"/api/todos/{milk['id']}", json={"done": False})
    eggs = local.get("/api/todos").json()[1]
    local.patch(f"/api/todos/{eggs['id']}", json={"position": 0})
    assert [t["text"] for t in local.get("/api/todos").json()] == ["eggs", "milk"]


def test_a_due_time_in_plain_words(local):
    todo = local.post("/api/todos", json={"text": "call the bank", "due": "tomorrow at 10am"}).json()
    due = datetime.fromtimestamp(todo["due_at"])
    assert (due.hour, due.minute) == (10, 0) and due.date() > datetime.now().date()
    r = local.post("/api/todos", json={"text": "x", "due": "whenever"})
    assert r.status_code == 400 and r.json()["error"]["hint"]


def test_lists_keep_their_to_dos_safe(local):
    [default] = local.get("/api/lists").json()
    assert local.delete(f"/api/lists/{default['id']}").status_code == 409  # the last list
    work = local.post("/api/lists", json={"name": "Work"}).json()
    assert local.post("/api/lists", json={"name": "work"}).status_code == 409
    todo = local.post("/api/todos", json={"text": "report", "list_id": work["id"]}).json()
    assert local.delete(f"/api/lists/{work['id']}").status_code == 409  # still has to-dos
    local.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert local.delete(f"/api/lists/{work['id']}").status_code == 200
    assert local.patch("/api/todos/999", json={"done": True}).status_code == 404
    assert local.post("/api/todos", json={"text": "x", "priority": "someday"}).status_code == 400


# ---------- reminders ----------


def test_a_reminder_in_plain_words(local):
    r = local.post("/api/reminders", json={"text": "stretch", "when": "in 2 hours"}).json()
    assert abs(r["at"] - (time.time() + 7200)) < 60 and r["repeat"] == "none"
    assert r["when"].startswith(("today", "tomorrow"))
    weekly = local.post("/api/reminders", json={"text": "pay rent", "when": "every Monday 9am"}).json()
    assert weekly["repeat"] == "weekly" and datetime.fromtimestamp(weekly["at"]).weekday() == 0
    bad = local.post("/api/reminders", json={"text": "x", "when": "sometime"})
    assert bad.status_code == 400 and "couldn't tell when" in bad.json()["error"]["message"]
    past = local.post("/api/reminders", json={"text": "x", "at": time.time() - 60})
    assert past.status_code == 400 and "passed" in past.json()["error"]["message"]


def test_cancel_and_bring_back_a_reminder(local):
    r = local.post("/api/reminders", json={"text": "water plants", "when": "tomorrow at 8am"}).json()
    local.delete(f"/api/reminders/{r['id']}")
    assert local.get("/api/reminders").json() == []
    local.post(f"/api/reminders/{r['id']}/restore")
    assert [x["text"] for x in local.get("/api/reminders").json()] == ["water plants"]


# ---------- reminders going off ----------


def test_a_reminder_goes_off_once(local, reminders):
    r = local.post("/api/reminders", json={"text": "take the cake out", "at": time.time() + 600}).json()
    reminders.now = r["at"] - 1
    assert reminders.tick() == []
    reminders.now = r["at"] + 1
    [fired] = reminders.tick()
    assert reminders.shown == ["take the cake out"] and reminders.said == ["Reminder: take the cake out"]
    assert reminders.tick() == []  # once
    [waiting] = local.get("/api/reminders/due").json()  # the app's banner
    assert waiting["text"] == "take the cake out" and not waiting["active"]
    local.post(f"/api/reminders/{fired['id']}/ack")
    assert local.get("/api/reminders/due").json() == []


def test_a_repeating_reminder_moves_on(local, reminders):
    r = local.post("/api/reminders", json={"text": "pay rent", "when": "every Monday 9am"}).json()
    reminders.now = r["at"] + 5
    reminders.tick()
    [again] = local.get("/api/reminders").json()
    assert again["next_at"] - r["at"] == pytest.approx(7 * 24 * 3600, abs=3600)  # a week later (DST: ±1h)
    assert datetime.fromtimestamp(again["next_at"]).hour == 9


def test_snooze(local, reminders):
    r = local.post("/api/reminders", json={"text": "call mum", "at": time.time() + 60}).json()
    reminders.now = r["at"] + 1
    reminders.tick()
    snoozed = local.post(f"/api/reminders/{r['id']}/snooze", json={"minutes": 10}).json()
    assert snoozed["active"] and snoozed["acknowledged"] and abs(snoozed["next_at"] - (time.time() + 600)) < 60
    reminders.now = snoozed["next_at"] + 1
    assert [x["text"] for x in reminders.tick()] == ["call mum"]


def test_a_reminder_missed_while_the_server_was_off_still_goes_off_once(local, reminders):
    r = local.post("/api/reminders", json={"text": "dentist", "when": "every day at 8"}).json()
    reminders.now = r["at"] + 3 * 24 * 3600 + 60  # three days later
    [fired] = reminders.tick()
    assert fired["missed"] and reminders.shown == ["Missed: dentist"]
    assert reminders.tick() == []  # not once per missed day
    [again] = local.get("/api/reminders").json()
    assert again["next_at"] > reminders.now


def test_notifications_and_speaking_can_be_turned_off(local, reminders, set_settings):
    set_settings(reminder_notify=False, reminder_speak=False)
    r = local.post("/api/reminders", json={"text": "quiet one", "at": time.time() + 60}).json()
    reminders.now = r["at"] + 1
    reminders.tick()
    assert reminders.shown == [] and reminders.said == []
    assert [x["text"] for x in local.get("/api/reminders/due").json()] == ["quiet one"]  # still in the app


# ---------- from chat (scripted model) ----------

from conftest import sse, tool_call  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402


def chat(client, text: str) -> list[dict]:
    chat_id = client.post("/api/chats", json={}).json()["id"]
    return sse(client.post(f"/api/chats/{chat_id}/messages", json={"text": text}))


def told_model(model) -> str:
    """What the tools told the model last (their results)."""
    return " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")


def test_remind_me_from_chat_uses_the_users_own_words(local, model):
    model.script = [tool_call("set_reminder", text="pay rent", when="every Monday 9am"), AIMessage(content="Done.")]
    events = chat(local, "remind me every Monday at 9 to pay rent")
    [card] = [e for e in events if e["type"] == "reminder_set"]
    assert card["reminder"]["repeat"] == "weekly" and card["reminder"]["when"].endswith("every week")
    [stored] = local.get("/api/reminders").json()
    at = datetime.fromtimestamp(stored["at"])
    assert (at.weekday(), at.hour, at.minute) == (0, 9, 0)
    assert "now it is " + datetime.now().strftime("%A").lower() in model.seen[0][0].content.lower()  # the time too


def test_an_unclear_time_becomes_a_question_not_a_guess(local, model):
    model.script = [tool_call("set_reminder", text="call mum", when="sometime soon"), AIMessage(content="When?")]
    chat(local, "remind me to call mum sometime soon")
    assert "Ask the user when" in told_model(model)
    assert local.get("/api/reminders").json() == []


def test_notes_from_chat_add_to_a_note_with_the_same_title(local, model, notes_folder):
    model.script = [tool_call("add_note", title="Plumber", text="Ahmed 0300 1234567"), AIMessage(content="Saved.")]
    chat(local, "note: the plumber is Ahmed, 0300 1234567")
    model.script = [tool_call("add_note", title="plumber", text="Comes on Tuesdays"), AIMessage(content="Added.")]
    events = chat(local, "add to the plumber note that he comes on Tuesdays")
    [card] = [e for e in events if e["type"] == "note_saved"]
    assert card["added_to"] is True
    text = (notes_folder / "Plumber.md").read_text()
    assert "1234567" in text and "Tuesdays" in text
    local.post(f"/api/actions/{card['action_id']}/undo", json={})
    assert "Tuesdays" not in (notes_folder / "Plumber.md").read_text()


def test_to_dos_from_chat(local, model):
    model.script = [
        tool_call("add_todo", text="milk", list="Shopping"),
        tool_call("add_todo", text="call the bank", due="tomorrow at 10am", priority="high"),
        AIMessage(content="Added both."),
    ]
    events = chat(local, "add milk to my shopping list, and I must call the bank tomorrow at 10")
    added = [e["todo"] for e in events if e["type"] == "todo_added"]
    assert [(t["text"], t["list"]) for t in added] == [("milk", "Shopping"), ("call the bank", "To-do")]
    assert added[1]["priority"] == 3 and datetime.fromtimestamp(added[1]["due_at"]).hour == 10

    model.script = [tool_call("show_todos"), tool_call("complete_todo", todo="2"), AIMessage(content="Done.")]
    events = chat(local, "what do I have to do? the second one is done")
    [shown] = [e for e in events if e["type"] == "todos"]
    numbered = [t["text"] for t in shown["todos"]]
    [done] = [e["todo"] for e in events if e["type"] == "todo_done"]
    assert done["text"] == numbered[1]


def test_completing_by_words_asks_when_several_match(local, model):
    local.post("/api/todos", json={"text": "pay electricity bill"})
    local.post("/api/todos", json={"text": "pay water bill"})
    model.script = [tool_call("complete_todo", todo="bill"), AIMessage(content="Which one?")]
    chat(local, "the bill is done")
    assert "Ask the user which one" in told_model(model)
    assert len(local.get("/api/todos").json()) == 2
    model.script = [tool_call("complete_todo", todo="water"), AIMessage(content="Done.")]
    chat(local, "the water bill is paid")
    assert [t["text"] for t in local.get("/api/todos").json()] == ["pay electricity bill"]


def test_cancel_a_reminder_from_chat(local, model):
    local.post("/api/reminders", json={"text": "gym", "when": "every day at 7am"})
    model.script = [tool_call("show_todos"), tool_call("cancel_reminder", reminder="1"), AIMessage(content="OK.")]
    events = chat(local, "cancel my gym reminder")
    assert [e["reminder"]["text"] for e in events if e["type"] == "reminder_cancelled"] == ["gym"]
    assert local.get("/api/reminders").json() == []


def test_a_time_the_model_made_up_is_not_used(local, model):
    """Small models add details: "tonight" -> "tonight at 11pm". The user's own words win."""
    model.script = [tool_call("set_reminder", text="lock the car", when="tonight at 11pm"), AIMessage(content="OK")]
    chat(local, "remind me tonight to lock the car")
    [r] = local.get("/api/reminders").json()
    assert datetime.fromtimestamp(r["at"]).hour == 20  # "tonight" means 20:00, not the model's 23:00


def test_a_one_off_day_does_not_become_a_weekly_reminder(local, model):
    model.script = [tool_call("set_reminder", text="send the report", when="Friday"), AIMessage(content="OK")]
    chat(local, "Remind me on Friday to send the report")
    [r] = local.get("/api/reminders").json()
    assert r["repeat"] == "none" and datetime.fromtimestamp(r["at"]).weekday() == 4


def test_a_list_named_by_the_user_is_used_when_the_model_leaves_it_out(local, model):
    local.post("/api/lists", json={"name": "Shopping"})
    model.script = [tool_call("add_todo", text="milk"), AIMessage(content="Added.")]
    chat(local, "Add milk to my shopping list")
    assert [(t["text"], t["list"]) for t in local.get("/api/todos").json()] == [("milk", "Shopping")]


def test_a_to_do_copied_with_the_whole_request_is_trimmed(local, model):
    local.post("/api/lists", json={"name": "Shopping"})
    model.script = [tool_call("add_todo", text="add eggs to shopping"), AIMessage(content="Added.")]
    chat(local, "add eggs to shopping")
    assert [(t["text"], t["list"]) for t in local.get("/api/todos").json()] == [("eggs", "Shopping")]


@pytest.mark.parametrize(
    "text",
    [
        "Note: the plumber is Ahmed",
        "write down that the wifi password is sunflower42",
        "remember that Sara's shoe size is 38",
        "make a note: ideas for the trip",
        "jot down the meeting time",
        "remind me tomorrow at 5 to call the dentist",
        "set a reminder for my mum's birthday",
        "add milk to my shopping list",
        "put 'fix the tap' on my to-do list",
        "what do I have to do?",
        "mark the electricity bill as done",
        "cancel my gym reminder",
        "stop reminding me about the plants",
        "don't let me forget the passport",
    ],
)
def test_clear_planner_requests_are_recognised(text):
    from conftest import wants_planner

    assert wants_planner(text)


@pytest.mark.parametrize(
    "text",
    [
        "where is my invoice for the garden furniture?",
        "find my notes about the budget review",
        "open the lentil soup recipe",
        "show me pictures from the holiday",
        "make a folder called Taxes in Documents",
        "what does the library letter say?",
        "find the video where someone says remember the milk",
    ],
)
def test_file_questions_keep_all_tools(text):
    from conftest import wants_planner

    assert not wants_planner(text)


def test_a_list_the_user_never_mentioned_is_not_used(local, model):
    local.post("/api/lists", json={"name": "Shopping"})
    model.script = [tool_call("add_todo", text="pay the electricity bill", list="Shopping"), AIMessage(content="OK")]
    chat(local, "new todo pay the electricity bill by Friday")
    assert [(t["text"], t["list"]) for t in local.get("/api/todos").json()] == [("pay the electricity bill", "To-do")]


def test_a_to_do_named_inside_a_whole_sentence_is_found(local, model):
    local.post("/api/todos", json={"text": "fix the tap"})
    model.script = [tool_call("complete_todo", todo="mark fix the tap as done"), AIMessage(content="Done.")]
    chat(local, "mark fix the tap as done")
    assert local.get("/api/todos").json() == []


def test_every_day_said_by_the_user_is_kept_when_the_model_moves_it_into_the_text(local, model):
    model.script = [tool_call("set_reminder", text="drink water every day", when="at 11am"), AIMessage(content="OK")]
    chat(local, "can you remind me to drink water every day at 11am")
    [r] = local.get("/api/reminders").json()
    assert r["repeat"] == "daily" and datetime.fromtimestamp(r["at"]).hour == 11


def test_the_same_to_do_twice_is_not_a_question(local, model):
    local.post("/api/todos", json={"text": "milk"})
    local.post("/api/todos", json={"text": "Milk"})
    model.script = [tool_call("complete_todo", todo="milk"), AIMessage(content="Done.")]
    chat(local, "I bought the milk")
    assert len(local.get("/api/todos").json()) == 1
