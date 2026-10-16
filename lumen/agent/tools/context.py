"""What the agent's tools share within one chat."""

from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote

from ...fileops.access import allowed


class ToolContext:
    """`last_results` remembers the latest results so "open the second one" can be resolved to a
    real path (the API shares it, so results shown by app buttons count too). `emit(event)`
    receives structured results for the app's cards, next to the text the model sees."""

    def __init__(
        self, emit: Callable[[dict], None] | None = None, app: bool = False, state: dict | None = None
    ) -> None:
        self.last_results: list[str] = (state if state is not None else {}).setdefault("last_results", [])
        self.emit = emit or (lambda event: None)
        self.app = app

    def resolve(self, target: str) -> Path:
        """A path, or a result number from the latest results ("2"), checked to be inside the indexed folders."""
        t = target.strip().lstrip("#")
        if t.isdigit():
            n = int(t)
            if not self.last_results:
                raise ValueError("No previous search results. Search first.")
            if not 1 <= n <= len(self.last_results):
                raise ValueError(f"Result number must be between 1 and {len(self.last_results)}.")
            return allowed(self.last_results[n - 1])
        path = allowed(target)
        if not path.exists() and "%" in target:
            path = allowed(unquote(target))  # model sent a URL-encoded path ("%20" for spaces)
        return path
