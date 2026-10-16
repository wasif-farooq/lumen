"""Chats with the agent (scripted model), and file changes: approve, cancel, undo."""

from langchain_core.messages import AIMessage

from conftest import agent_tool_names, sse, tool_call


def new_chat(client) -> str:
    return client.post("/api/chats", json={}).json()["id"]


def ask(client, chat_id, text):
    r = client.post(f"/api/chats/{chat_id}/messages", json={"text": text})
    assert r.status_code == 200
    return sse(r)


def types(events):
    return [e["type"] for e in events]


def test_a_search_turn_streams_tool_call_results_and_answer(indexed, local, model):
    model.script = [tool_call("search_files", query="invoice"), AIMessage(content="Found your invoice.")]
    chat = new_chat(local)
    events = ask(local, chat, "where is my invoice?")
    assert types(events) == ["started", "tool_call", "results", "answer", "done"]
    assert events[1] == {"type": "tool_call", "name": "search_files", "args": {"query": "invoice"}}
    assert events[2]["hits"][0]["name"] == "invoice-1042.pdf"
    assert events[3]["text"] == "Found your invoice."


def test_history_and_title_are_kept(indexed, local, model):
    model.script = [AIMessage(content="Hello!")]
    chat = new_chat(local)
    ask(local, chat, "hi there, can you help me find a recipe for soup please?")
    [c] = local.get("/api/chats").json()
    assert c["title"].startswith("hi there, can you help me") and c["title"].endswith("…")
    history = local.get(f"/api/chats/{chat}/events").json()
    assert [e["type"] for e in history] == ["user", "answer"]
    local.delete(f"/api/chats/{chat}")
    assert local.get("/api/chats").json() == []


def test_bad_requests(indexed, local, model):
    assert local.post("/api/chats/nope/messages", json={"text": "hi"}).status_code == 404
    chat = new_chat(local)
    assert local.post(f"/api/chats/{chat}/messages", json={"text": "  "}).status_code == 400
    assert local.post(f"/api/chats/{chat}/approve", json={"approved": True}).status_code == 409


def test_model_errors_become_a_message_not_a_broken_stream(indexed, local, model, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr(type(model), "_generate", boom)
    events = ask(local, new_chat(local), "hello")
    assert types(events) == ["started", "error", "done"]
    assert "Can't reach the local model" in events[1]["text"]


def test_a_change_waits_for_approval_then_happens_and_can_be_undone(indexed, local, model):
    target = indexed.documents / "Reports"
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="Created it.")]
    chat = new_chat(local)
    events = ask(local, chat, "make a Reports folder in Documents")
    assert types(events)[-2:] == ["approval", "done"]
    assert events[-2]["op"] == "create_folder" and not target.exists()
    assert local.get(f"/api/chats/{chat}/pending").json()["pending"]["op"] == "create_folder"

    done = sse(local.post(f"/api/chats/{chat}/approve", json={"approved": True}))
    assert "action_done" in types(done) and target.is_dir()
    action = next(e for e in done if e["type"] == "action_done")
    assert local.get("/api/actions").json()[0]["id"] == action["id"]

    r = local.post(f"/api/actions/{action['id']}/undo", json={"chat_id": chat})
    assert r.status_code == 200 and not target.exists()


def test_cancelled_change_does_nothing(indexed, local, model):
    target = indexed.documents / "Never"
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="OK, not doing it.")]
    chat = new_chat(local)
    ask(local, chat, "make a folder")
    events = sse(local.post(f"/api/chats/{chat}/approve", json={"approved": False}))
    assert "action_done" not in types(events) and not target.exists()


def test_moving_a_file_keeps_it_searchable_and_undo_moves_it_back(indexed, local, model):
    src = indexed.files["recipe"]
    dst = indexed.documents / "lentil-soup.md"
    model.script = [tool_call("move_file", source=str(src), destination=str(indexed.documents)), AIMessage(content="Moved.")]
    chat = new_chat(local)
    ask(local, chat, "move the soup recipe to Documents")
    done = sse(local.post(f"/api/chats/{chat}/approve", json={"approved": True}))
    assert dst.exists() and not src.exists()
    [hit] = local.get("/api/search", params={"q": "lentils"}).json()
    assert hit["path"] == str(dst)
    action = next(e for e in done if e["type"] == "action_done")
    local.post(f"/api/actions/{action['id']}/undo", json={})
    assert src.exists() and not dst.exists()


def test_changes_outside_indexed_folders_are_refused(indexed, local, model, tmp_path):
    outside = tmp_path / "outside"
    model.script = [tool_call("create_folder", path=str(outside)), AIMessage(content="I can't do that.")]
    events = ask(local, new_chat(local), "make a folder outside")
    assert "approval" not in types(events) and not outside.exists()
    assert "outside your indexed folders" in model.seen[-1][-1].content  # the tool told the model why


def test_never_overwrites(indexed, local, model):
    existing = indexed.files["notes"]
    model.script = [tool_call("create_file", path=str(existing), content="new"), AIMessage(content="Exists.")]
    events = ask(local, new_chat(local), "overwrite the notes")
    assert "approval" not in types(events)
    assert "printer paper" in existing.read_text()


def test_test_mode_reports_instead_of_changing(indexed, local, model, set_settings):
    set_settings(write_enabled=False)
    target = indexed.documents / "DryRun"
    model.script = [tool_call("create_folder", path=str(target)), AIMessage(content="Done (test mode).")]
    chat = new_chat(local)
    ask(local, chat, "make a folder")
    done = sse(local.post(f"/api/chats/{chat}/approve", json={"approved": True}))
    action = next(e for e in done if e["type"] == "action_done")
    assert action["dry_run"] is True and not target.exists()


def test_the_agent_has_no_way_to_delete(env):
    names = agent_tool_names()
    assert names  # sanity
    assert not [n for n in names if any(w in n for w in ("delete", "remove", "trash", "unlink"))]
