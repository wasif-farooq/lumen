"""The agent: a LangGraph loop of (model -> tools -> model)."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ..core.settings import settings
from ..providers import backends
from .prompts import APP_NOTE, SYSTEM_PROMPT
from .tools import make_tools
from .tools.planner import NAMES as PLANNER_TOOLS
from .tools.planner import wanted as wants_planner


def build_agent(
    checkpointer: BaseCheckpointSaver | None = None,
    emit: Callable[[dict], None] | None = None,
    app: bool = False,
    state: dict | None = None,
) -> CompiledStateGraph:
    on_cpu: dict[str, Any] = {"num_gpu": 0} if settings.cpu_only else {}
    llm = backends.chat_model(
        num_ctx=settings.num_ctx,
        temperature=0,
        reasoning=False,  # no "thinking" before tool calls: much faster on a small GPU
        keep_alive="30m",
        **on_cpu,
    )
    tools = make_tools(emit, app=app, state=state)
    llm_with_tools = llm.bind_tools(tools)
    # A message clearly about notes, to-dos or reminders gets only those tools (see tools.planner)
    llm_planner = llm.bind_tools([t for t in tools if t.name in PLANNER_TOOLS])
    extra = APP_NOTE if app else ""
    if settings.open_mode != "xdg":
        extra += (
            "\n- TEST MODE: open_file and show_in_folder cannot open anything here. Never say a file "
            "was opened; say it was not opened (test mode) and give its full path."
        )

    def prompt() -> str:
        """The rules with the time now (a chat can stay open for days; reminders need the time)."""
        now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
        return SYSTEM_PROMPT.format(now=now, roots=", ".join(map(str, settings.roots))) + extra

    def agent(state: MessagesState) -> dict:
        system = prompt()
        msgs = _recent_turns(state["messages"], turns=4)
        if _repeating(msgs):
            # Small models sometimes retry the same failing call forever: make it answer instead
            nudge = SystemMessage(
                "You already made this exact tool call. Do not call tools again; "
                "answer the user with what you have, including any error."
            )
            return {"messages": [_answer_only(llm.invoke([SystemMessage(system), *msgs, nudge]))]}
        if _tool_steps(msgs) >= MAX_TOOL_STEPS:
            # ...or keeps searching with new synonyms until the step limit ends the turn with an error
            nudge = SystemMessage(
                "You have used tools enough for this question. Do not call tools again; answer the "
                "user with what you found, or say that nothing was found."
            )
            return {"messages": [_answer_only(llm.invoke([SystemMessage(system), *msgs, nudge]))]}
        asked = next((str(m.content) for m in reversed(msgs) if isinstance(m, HumanMessage)), "")
        chosen = llm_planner if wants_planner(asked) else llm_with_tools
        return {"messages": [chosen.invoke([SystemMessage(system), *msgs])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


MAX_TOOL_STEPS = 5  # tool-calling steps in one turn before the model must answer (the limit is 16 steps)


def _answer_only(reply: BaseMessage) -> BaseMessage:
    """After a nudge to answer, an answer: any tool call that still comes back is dropped."""
    if isinstance(reply, AIMessage) and reply.tool_calls:
        return AIMessage(content=str(reply.content) or "I couldn't find anything for that.")
    return reply


def _tool_steps(messages: Sequence[BaseMessage]) -> int:
    """How many tool-calling steps the model has taken since the user's last message."""
    n = 0
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.tool_calls:
            n += 1
    return n


def _repeating(messages: Sequence[BaseMessage]) -> bool:
    """True when the last two tool-calling steps (in this turn) asked for exactly the same calls."""
    calls = []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.tool_calls:
            calls.append([(c["name"], sorted(c["args"].items())) for c in m.tool_calls])
    return len(calls) >= 2 and calls[0] == calls[1]


def _recent_turns(messages: Sequence[BaseMessage], turns: int) -> Sequence[BaseMessage]:
    """Keep only the last few user turns so a small context window doesn't overflow."""
    human_idx = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    start = human_idx[-turns] if len(human_idx) >= turns else 0
    return messages[start:]
