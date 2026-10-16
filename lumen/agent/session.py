"""One chat with the agent: its memory (thread), streaming, approvals, and Langfuse tracing."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from .graph import build_agent

# What a turn yields: ("tool_call", (name, args)), ("ui", dict), ("approval", plan), ("answer", text)…
AgentEvent = tuple[str, Any]


class Session:
    """One chat: keeps conversation memory (thread) and Langfuse session together."""

    def __init__(
        self, thread_id: str | None = None, checkpointer: BaseCheckpointSaver | None = None, app: bool = False
    ) -> None:
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

    def stream(self, text: str) -> Iterator[AgentEvent]:
        """Yield (kind, payload) events: ("tool_call", (name, args)), ("tool_result", str), ("answer", str),
        structured ("ui", dict) events from tools (search hits, opened files) for app UIs, and
        ("approval", plan) when a change waits for the user: answer it with resume()."""
        yield from self._run({"messages": [HumanMessage(text)]})

    def resume(self, approved: bool) -> Iterator[AgentEvent]:
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

    def _run(self, graph_input: dict | Command) -> Iterator[AgentEvent]:
        cfg: RunnableConfig = {
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

    def close(self) -> None:
        if self.callbacks:
            from langfuse import get_client

            get_client().flush()
