"""Plans for changes: check a request and describe it. Nothing changes yet; the user approves first."""

import os
from pathlib import Path

from ..core.formatting import human_size
from ..core.settings import settings

MAX_TEXT_BYTES = 1024 * 1024  # create_file: text only, up to 1 MB
MAX_COPY_BYTES = 20 * 1024**3  # refuse copies over 20 GB


class FileOpError(ValueError):
    """A request that can't be done as asked; the message is for the user."""


def _inside(p: Path) -> Path:
    p = Path(os.path.expanduser(str(p))).resolve()
    if not any(p == r or p.is_relative_to(r) for r in settings.roots):
        raise FileOpError(f"{p} is outside your indexed folders ({', '.join(map(str, settings.roots))}).")
    return p


def _not_a_root(p: Path):
    if p in settings.roots:
        raise FileOpError(f"{p} is one of your indexed folders itself; I won't move it.")


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _target(src: Path, destination: str) -> Path:
    """Destination path; an existing folder means 'put it inside that folder'."""
    dst = _inside(Path(destination))
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists():
        raise FileOpError(f"{dst} already exists. I never overwrite; pick another name or folder.")
    if not dst.parent.is_dir():
        raise FileOpError(f"The folder {dst.parent} doesn't exist. Create it first.")
    if src.is_dir() and (dst == src or dst.is_relative_to(src)):
        raise FileOpError("Can't put a folder inside itself.")
    return dst


def plan_create_folder(path: str) -> dict:
    p = _inside(Path(path))
    if p.exists():
        raise FileOpError(f"{p} already exists.")
    return {"op": "create_folder", "dst": str(p), "summary": f"Create folder {p}"}


def plan_create_file(path: str, content: str) -> dict:
    p = _inside(Path(path))
    if p.exists():
        raise FileOpError(f"{p} already exists. I never overwrite.")
    if not p.parent.is_dir():
        raise FileOpError(f"The folder {p.parent} doesn't exist. Create it first.")
    data = content.encode("utf-8")
    if len(data) > MAX_TEXT_BYTES:
        raise FileOpError("That text is over 1 MB; I only create small text files.")
    preview = content if len(content) <= 400 else content[:400] + "…"
    return {
        "op": "create_file",
        "dst": str(p),
        "content": content,
        "size": len(data),
        "summary": f"Create file {p} ({human_size(len(data))})",
        "preview": preview,
    }


def plan_copy(source: str, destination: str) -> dict:
    src = _inside(Path(source))
    if not src.exists():
        raise FileOpError(f"{src} doesn't exist.")
    dst = _target(src, destination)
    size = _size(src)
    if size > MAX_COPY_BYTES:
        raise FileOpError(f"That is {human_size(size)}; I don't copy more than {human_size(MAX_COPY_BYTES)} at once.")
    kind = "folder" if src.is_dir() else "file"
    return {
        "op": "copy",
        "src": str(src),
        "dst": str(dst),
        "size": size,
        "summary": f"Copy {kind} {src} → {dst} ({human_size(size)})",
    }


def plan_move(source: str, destination: str) -> dict:
    src = _inside(Path(source))
    if not src.exists():
        raise FileOpError(f"{src} doesn't exist.")
    _not_a_root(src)
    dst = _target(src, destination)
    kind = "folder" if src.is_dir() else "file"
    verb = "Rename" if src.parent == dst.parent else "Move"
    return {
        "op": "move",
        "src": str(src),
        "dst": str(dst),
        "size": _size(src),
        "summary": f"{verb} {kind} {src} → {dst}",
    }
