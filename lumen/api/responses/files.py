"""Answers about files and search."""

from .common import Out


class HitOut(Out):
    """A file found by a search."""

    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    snippet: str = ""
    duration: float | None = None
    at: float | None = None  # where in a video/audio the words are said (seconds)
    at_text: str = ""
    partial: bool = False


class ImageHitOut(HitOut):
    score: float  # how well it matched (higher is better)


class SegmentOut(Out):
    start: float
    end: float
    text: str
    time: str


class FileInfoOut(Out):
    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    folder: str
    indexed: bool
    searchable: bool
    caption: str
    duration: float | None
    excerpt: str
    segments: list[SegmentOut]
