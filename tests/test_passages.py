"""Answers from the right part of the right file: passages and read_file with a question."""

import re

from conftest import index_now, sse, tool_call
from langchain_core.messages import AIMessage, ToolMessage

CV = "\n\n".join(
    [
        "Curriculum vitae of Alex Example. " + "Summary of skills and interests. " * 60,
        "09/2012 - 05/2015 Software engineer at Acme Rockets, Springfield. Built launch planning tools.",
        "Hobbies: sailing, chess and long walks. " * 60,
        "06/2015 - present Team lead at Globex Corporation, Shelbyville. Leads the data platform team.",
        "References available on request. " * 60,
    ]
)
assert len(CV) > 6000  # longer than read_file's largest budget, so it has to pick parts


def passages_of(out: str) -> list[str]:
    """The passage blocks of a find_in_files result, best first ("[1] file (part …)" each)."""
    return re.split(r"\n\n(?=\[\d+\] )", out.split("\n\n", 1)[1])


def tool_output(local, model, call) -> tuple[str, list[dict]]:
    """Run one tool through a chat; return what the tool told the model and the streamed events."""
    model.script = [call, AIMessage(content="ok")]
    chat = local.post("/api/chats", json={}).json()["id"]
    events = sse(local.post(f"/api/chats/{chat}/messages", json={"text": "question"}))
    [msg] = [m for m in model.seen[-1] if isinstance(m, ToolMessage)][-1:]
    return msg.content, events


def test_find_in_files_finds_the_passage_for_a_year_inside_a_date_range(env, local, model):
    (env.documents / "cv.txt").write_text(CV)
    index_now()
    out, events = tool_output(local, model, tool_call("find_in_files", question="where did I work in 2014?"))
    assert "Acme Rockets" in passages_of(out)[0]  # the best passage comes first
    assert "cv.txt" in out
    [results] = [e for e in events if e["type"] == "results"]
    assert results["hits"][0]["name"] == "cv.txt"


def test_find_in_files_with_no_match(env, local, model):
    index_now()
    out, _ = tool_output(local, model, tool_call("find_in_files", question="submarine periscope maintenance"))
    assert out.startswith("No passage matches")


def test_read_file_returns_a_short_file_whole(indexed, local, model):
    out, _ = tool_output(local, model, tool_call("read_file", target=str(indexed.files["notes"])))
    assert "complete" in out and "printer paper" in out


def test_read_file_with_a_question_returns_the_relevant_parts_of_a_long_file(env, local, model):
    cv = env.documents / "cv.txt"
    cv.write_text(CV)
    index_now()
    out, _ = tool_output(local, model, tool_call("read_file", target=str(cv), question="team lead Globex"))
    assert "most relevant to the question" in out
    assert "Globex Corporation" in out
    assert "were NOT read" in out  # the model is told it hasn't seen everything


def test_read_file_without_a_question_says_what_was_left_out(env, local, model):
    cv = env.documents / "cv.txt"
    cv.write_text(CV)
    index_now()
    out, _ = tool_output(local, model, tool_call("read_file", target=str(cv)))
    assert "showing the first" in out and "The rest was NOT read" in out


def test_read_file_of_a_file_without_text(indexed, local, model):
    out, _ = tool_output(local, model, tool_call("read_file", target=str(indexed.files["image"])))
    assert "no readable text" in out
