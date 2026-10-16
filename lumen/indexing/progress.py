"""How an index run reports what it is doing (Observer).

The pipeline calls a `Progress`; what happens with it is up to the listener: the CLI prints it
for people, `EventStream` writes the machine-readable lines the server turns into the app's
progress view. `parse_event` reads those lines back.
"""

import json

EVENT_PREFIX = "@@"


class Progress:
    """Listens to an index run. This base class ignores everything (handy as a default)."""

    def phase(self, name: str):
        """A pass starts: scan, captions, visual, media, passages."""

    def scanned(self, count: int):
        """Files checked so far by the scan (every 500)."""

    def item(self, done: int, total: int, path: str, note: str):
        """An AI pass finished (or reports on) one file."""

    def paused(self, is_paused: bool):
        """The run holds for a pause from the app, or continues."""

    def summary(self, stats: dict):
        """The run is done."""


class Several(Progress):
    """Tells every listener."""

    def __init__(self, *listeners: Progress):
        self.listeners = listeners

    def phase(self, name):
        for p in self.listeners:
            p.phase(name)

    def scanned(self, count):
        for p in self.listeners:
            p.scanned(count)

    def item(self, done, total, path, note):
        for p in self.listeners:
            p.item(done, total, path, note)

    def paused(self, is_paused):
        for p in self.listeners:
            p.paused(is_paused)

    def summary(self, stats):
        for p in self.listeners:
            p.summary(stats)


class EventStream(Progress):
    """One '@@{json}' line per event on stdout, for the server that started the run."""

    def _emit(self, **event):
        print(EVENT_PREFIX + json.dumps(event, default=str), flush=True)

    def phase(self, name):
        self._emit(phase=name)

    def scanned(self, count):
        self._emit(scanned=count)

    def item(self, done, total, path, note):
        self._emit(item={"done": done, "total": total, "path": path, "note": note[:300]})

    def paused(self, is_paused):
        self._emit(paused=is_paused)

    def summary(self, stats):
        self._emit(summary=stats)


def parse_event(line: str) -> dict | None:
    """The event in a line from EventStream, or None for ordinary output (or a garbled line)."""
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        event = json.loads(line[len(EVENT_PREFIX) :])
    except ValueError:
        return None
    return event if isinstance(event, dict) else None
