"""Finder agent: a LangGraph loop of (model -> tools -> model) on a local Ollama model."""

import os
import uuid
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from . import providers
from .tools import make_tools
from .core.settings import settings

SYSTEM_PROMPT = """You are Finder, a local assistant that finds and opens the user's files.
Today is {today}. Indexed folders: {roots}.

Rules:
- To find files ALWAYS call search_files. Never invent file names or paths.
- Turn time words into dates (YYYY-MM-DD): "last month", "this week", "yesterday".
- Use ext for file types: pdf, docx, xlsx, and "jpg,jpeg,png,webp" for images.
- Images and scanned PDFs are indexed by an AI description of what they show, so search them
  by content words (e.g. "identity card", "receipt", "screenshot"). Descriptions can misread names.
- Videos/audio are indexed with length, a description of what they show and a transcript of what is said.
  Video extensions: "mp4,mkv,mov,avi,webm". Use min_minutes/max_minutes for length.
  When a result says "said at start_seconds=754 (12:34)" and the user wants to see/hear it, call open_file
  with start_seconds=754.
- If a search finds nothing, try again with synonyms (CV -> resume) or fewer words or no filters.
- "open it", "show me that file", "the second one" refer to the latest search results:
  pass the result number (e.g. "2") or the full path to open_file.
- If the user asks to open/show a file and several results match equally, list them and ask which one.
  If one result is clearly the best match, open it.
- Only call open_file / show_in_folder when the user asks to open, show or view a file.
  "show me / open / view that file" means open_file. Use show_in_folder only when the user asks for
  the folder or where the file is located.
- Questions about FACTS in the user's files (dates, jobs, places, amounts, names, numbers; e.g.
  "where did I work in 2014?"): call find_in_files with the question. It searches inside ALL files.
- To answer about one specific file, call read_file with question= set to the user's question
  (do not open it). Read results say whether you saw the complete file.
- Never say something is not in a file unless you saw the complete file. If you only saw parts,
  say what you found and that the rest was not checked, or search more with find_in_files.
- Years inside ranges count: "01/2014 - 05/2019" includes 2014.
- Pictures by what they show ("photos of the beach", "my passport picture"): search_images.
  "Images like this one / similar photos": find_similar_images.
- Changes: create_folder, create_file (small text files), copy_file, move_file (also renames).
  Each one shows the user an approval request; call it once and wait for the result.
  Use full paths; for "move it/that file" use the result number. You can NOT delete files.
- Reply briefly. Show file name and full path for each file you mention."""


APP_NOTE = """
- The user sees every search result as a card (name, path, size, date, matching text) right under
  your message. Do NOT list files or paths again: reply in 1-2 short sentences, naming the best match."""


def build_agent(checkpointer=None, emit=None, app=False, state=None):
    llm = providers.chat_model(
        num_ctx=settings.num_ctx,
        temperature=0,
        reasoning=False,  # no "thinking" before tool calls: much faster on a small GPU
        keep_alive="30m",
        **({"num_gpu": 0} if settings.cpu_only else {}),
    )
    tools = make_tools(emit, app=app, state=state)
    llm_with_tools = llm.bind_tools(tools)
    system = SYSTEM_PROMPT.format(today=date.today().isoformat(), roots=", ".join(map(str, settings.roots)))
    if app:
        system += APP_NOTE
    if settings.open_mode != "xdg":
        system += ("\n- TEST MODE: open_file and show_in_folder cannot open anything here. Never say a file "
                   "was opened; say it was not opened (test mode) and give its full path.")

    def agent(state: MessagesState):
        msgs = _recent_turns(state["messages"], turns=4)
        if _repeating(msgs):
            # Small models sometimes retry the same failing call forever: make it answer instead
            nudge = SystemMessage("You already made this exact tool call. Do not call tools again; "
                                  "answer the user with what you have, including any error.")
            return {"messages": [llm.invoke([SystemMessage(system), *msgs, nudge])]}
        return {"messages": [llm_with_tools.invoke([SystemMessage(system), *msgs])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _repeating(messages) -> bool:
    """True when the last two tool-calling steps (in this turn) asked for exactly the same calls."""
    calls = []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.tool_calls:
            calls.append([(c["name"], sorted(c["args"].items())) for c in m.tool_calls])
    return len(calls) >= 2 and calls[0] == calls[1]


def _recent_turns(messages, turns: int):
    """Keep only the last few user turns so a small context window doesn't overflow."""
    human_idx = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    start = human_idx[-turns] if len(human_idx) >= turns else 0
    return messages[start:]


class Session:
    """One chat: keeps conversation memory (thread) and Langfuse session together."""

    def __init__(self, thread_id: str | None = None, checkpointer=None, app=False):
        self._ui_events: list[dict] = []
        self.state: dict = {}  # tool state shared with the API (last results)
        self.graph = build_agent(checkpointer, emit=self._ui_events.append, app=app, state=self.state)
        self.thread_id = thread_id or str(uuid.uuid4())
        self.callbacks = []
        if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
            from langfuse.langchain import CallbackHandler

            self.callbacks.append(CallbackHandler())

    @property
    def tracing(self) -> bool:
        return bool(self.callbacks)

    def stream(self, text: str):
        """Yield (kind, payload) events: ("tool_call", (name, args)), ("tool_result", str), ("answer", str),
        structured ("ui", dict) events from tools (search hits, opened files) for app UIs, and
        ("approval", plan) when a change waits for the user: answer it with resume()."""
        yield from self._run({"messages": [HumanMessage(text)]})

    def resume(self, approved: bool):
        """Continue after an approval request: the waiting tool runs (or is cancelled)."""
        yield from self._run(Command(resume={"approved": approved}))

    @property
    def waiting(self) -> dict | None:
        """The pending approval request, if the agent is paused on one."""
        snap = self.graph.get_state({"configurable": {"thread_id": self.thread_id}})
        for task in snap.tasks:
            for it in task.interrupts:
                return it.value
        return None

    def _run(self, graph_input):
        cfg = {
            "configurable": {"thread_id": self.thread_id},
            "callbacks": self.callbacks,
            "recursion_limit": 16,
            "metadata": {"langfuse_session_id": self.thread_id, "langfuse_tags": ["lumen", "finder"]},
            "run_name": "finder",
        }
        for update in self.graph.stream(graph_input, cfg, stream_mode="updates"):
            if "__interrupt__" in update:
                while self._ui_events:
                    yield "ui", self._ui_events.pop(0)
                for it in update["__interrupt__"]:
                    yield "approval", it.value
                return
            for node, data in update.items():
                for msg in data["messages"]:
                    if node == "agent":
                        for call in msg.tool_calls:
                            yield "tool_call", (call["name"], call["args"])
                        if not msg.tool_calls:
                            yield "answer", msg.content
                    else:
                        yield "tool_result", msg.content
                        while self._ui_events:
                            yield "ui", self._ui_events.pop(0)

    def close(self):
        if self.callbacks:
            from langfuse import get_client

            get_client().flush()
