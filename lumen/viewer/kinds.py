"""What a file is for the viewer, and how the app should show it."""

from pathlib import Path

from ..core.filetypes import AUDIO_EXTS, IMAGE_EXTS, TEXT_EXTS, VIDEO_EXTS

MARKDOWN = {"md", "markdown"}
PLAIN = {"txt", "log", "rst", "srt", "ini", "cfg", "conf", "tex"}  # text that isn't code
TABLES = {"xlsx", "ods", "csv", "tsv"}
SLIDES = {"pptx", "odp"}
DOCUMENTS = {"docx", "odt", "epub"}


def kind(ext: str) -> str:
    """pdf | image | markdown | text | code | document | table | slides | video | audio | other."""
    if ext == "pdf":
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in TABLES:
        return "table"
    if ext in SLIDES:
        return "slides"
    if ext in DOCUMENTS:
        return "document"
    if ext in MARKDOWN:
        return "markdown"
    if ext in PLAIN:
        return "text"
    if ext in TEXT_EXTS:
        return "code"
    return "other"


def describe(p: Path) -> dict:
    """The viewer's first look at a file: its kind and what the app needs to lay it out."""
    ext = p.suffix.lower().lstrip(".")
    k = kind(ext)
    info: dict = {"path": str(p), "name": p.name, "ext": ext, "kind": k, "size": p.stat().st_size}
    if k == "pdf":
        from . import pdf

        info["pages"] = pdf.page_count(p)
        info["shapes"] = pdf.page_shapes(p)  # height / width of each page
    elif k == "code":
        info["language"] = ext
    elif k in ("video", "audio"):
        from ..indexing.passes.video import probe

        try:
            info["duration"] = probe(str(p))["duration"]
        except Exception:  # unreadable media: the player finds out
            info["duration"] = None
    return info
