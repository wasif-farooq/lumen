"""Answers about index runs."""

from .common import Out


class IndexStarted(Out):
    running: bool


class IndexStopped(Out):
    stopped: bool
    running: bool


class IndexPausing(Out):
    pausing: bool
    running: bool


class RecentFile(Out):
    phase: str | None
    path: str
    note: str | None
    ext: str | None
    kind: str | None


class IndexProgressOut(Out):
    running: bool
    started: float | None
    phase: str | None
    done: int
    total: int
    path: str | None
    note: str | None
    scanned: int
    ext: str | None
    kind: str | None
    paused: bool
    pausing: bool
    summary: dict | None
    error: str | None  # set when the indexer process ended with an error
    eta: int | None  # seconds left in this step
    recent: list[RecentFile]
    lines: list[str]


class Excluded(Out):
    excluded: list[str]


class ExcludedAndRemoved(Excluded):
    removed: int


class Removed(Out):
    removed: int


class FolderPaused(Out):
    paused: bool
