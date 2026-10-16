"""Looking around the indexed folders and opening files on the desktop."""

import os

from langchain_core.tools import tool

from ...core.filetypes import MEDIA_EXTS, RUNNABLE_EXTS
from ...core.settings import settings
from ...fileops.access import allowed, launch
from .context import ToolContext


def build(ctx: ToolContext) -> dict:
    emit, resolve = ctx.emit, ctx.resolve

    @tool
    def list_dir(path: str) -> str:
        """List what is inside a folder.

        Args:
            path: full folder path.
        """
        folder = allowed(path)
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        entries = [e for e in entries if not e.name.startswith(".")]
        lines = [f"{'[dir] ' if e.is_dir() else ''}{e.name}" for e in entries[:100]]
        more = f"\n… and {len(entries) - 100} more" if len(entries) > 100 else ""
        return f"{folder}:\n" + "\n".join(lines) + more

    @tool
    def open_file(target: str, start_seconds: float = 0) -> str:
        """Open a file in its default app on the user's desktop (PDF viewer, LibreOffice, image viewer, video player).

        Args:
            target: full file path, or a result number from the last search (e.g. "1").
            start_seconds: video/audio only: start playing here; copy the start_seconds=N number from the search result.
        """
        path = resolve(target)
        if not path.exists():
            return f"File not found: {path}"
        ext = path.suffix.lower().lstrip(".")
        if path.is_file() and (ext in RUNNABLE_EXTS or os.access(path, os.X_OK)):
            return (
                f"{path.name} is a script/program; opening it could run it, so I showed its folder instead. "
                + launch(path.parent)
            )
        start = start_seconds if ext in MEDIA_EXTS else 0
        result = launch(path, start)
        emit({"type": "opened", "path": str(path), "start_seconds": start, "dry_run": settings.open_mode != "xdg"})
        return result

    @tool
    def show_in_folder(target: str) -> str:
        """Open the folder that contains a file in the file manager.

        Args:
            target: full file path, or a result number from the last search (e.g. "1").
        """
        path = resolve(target)
        return launch(path if path.is_dir() else path.parent)

    return {"list_dir": list_dir, "open_file": open_file, "show_in_folder": show_in_folder}
