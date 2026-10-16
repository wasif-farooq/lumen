"""File changes the agent may make, always after the user approves: create a folder or text file,
copy or move (rename) a file or folder. Never deletes, never overwrites; every change can be undone.

    plan_*()  -> checks the request and describes it (nothing changes yet)
    execute() -> does it, logs it for undo, keeps the search index in step
    undo()    -> reverses one logged change
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from .core.settings import settings



MAX_TEXT_BYTES = 1024 * 1024        # create_file: text only, up to 1 MB
MAX_COPY_BYTES = 20 * 1024 ** 3     # refuse copies over 20 GB


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


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------- plans (no changes yet) ----------

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
    return {"op": "create_file", "dst": str(p), "content": content, "size": len(data),
            "summary": f"Create file {p} ({human(len(data))})", "preview": preview}


def plan_copy(source: str, destination: str) -> dict:
    src = _inside(Path(source))
    if not src.exists():
        raise FileOpError(f"{src} doesn't exist.")
    dst = _target(src, destination)
    size = _size(src)
    if size > MAX_COPY_BYTES:
        raise FileOpError(f"That is {human(size)}; I don't copy more than {human(MAX_COPY_BYTES)} at once.")
    kind = "folder" if src.is_dir() else "file"
    return {"op": "copy", "src": str(src), "dst": str(dst), "size": size,
            "summary": f"Copy {kind} {src} → {dst} ({human(size)})"}


def plan_move(source: str, destination: str) -> dict:
    src = _inside(Path(source))
    if not src.exists():
        raise FileOpError(f"{src} doesn't exist.")
    _not_a_root(src)
    dst = _target(src, destination)
    kind = "folder" if src.is_dir() else "file"
    verb = "Rename" if src.parent == dst.parent else "Move"
    return {"op": "move", "src": str(src), "dst": str(dst), "size": _size(src),
            "summary": f"{verb} {kind} {src} → {dst}"}


# ---------- execute / undo ----------

def _log_file() -> Path:
    return settings.data_dir / "actions.jsonl"


def _append(entry: dict):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _log_file().open("a") as f:
        f.write(json.dumps(entry) + "\n")


def history() -> list[dict]:
    try:
        return [json.loads(line) for line in _log_file().read_text().splitlines() if line.strip()]
    except OSError:
        return []


def execute(plan: dict) -> dict:
    """Carry out an approved plan (re-checked, since files may have changed while waiting)."""
    op = plan["op"]
    fresh = {
        "create_folder": lambda: plan_create_folder(plan["dst"]),
        "create_file": lambda: plan_create_file(plan["dst"], plan["content"]),
        "copy": lambda: plan_copy(plan["src"], plan["dst"]),
        "move": lambda: plan_move(plan["src"], plan["dst"]),
    }[op]()
    if not settings.write_enabled:
        return {**fresh, "id": None, "dry_run": True, "message": f"TEST MODE, nothing changed: {fresh['summary']}"}
    src, dst = Path(fresh.get("src", "")), Path(fresh["dst"])
    if op == "create_folder":
        dst.mkdir(parents=True)
    elif op == "create_file":
        with dst.open("x", encoding="utf-8") as f:  # "x": fail rather than overwrite
            f.write(fresh["content"])
    elif op == "copy":
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    elif op == "move":
        shutil.move(str(src), str(dst))
        _reindex_moved(src, dst)
    entry = {"id": uuid.uuid4().hex[:12], "at": time.time(), "op": op, "src": fresh.get("src"), "dst": str(dst),
             "summary": fresh["summary"], "undone": False}
    _append(entry)
    return {**entry, "dry_run": False, "message": f"Done: {fresh['summary']}"}


def undo(action_id: str) -> str:
    """Reverse a logged change: move back, or send what was created/copied to the Trash (recoverable)."""
    entries = history()
    entry = next((e for e in entries if e["id"] == action_id), None)
    if not entry:
        raise FileOpError("No such change.")
    if entry.get("undone"):
        raise FileOpError("That change was already undone.")
    if not settings.write_enabled:
        raise FileOpError("Test mode: nothing to undo.")
    dst = Path(entry["dst"])
    if entry["op"] == "move":
        src = Path(entry["src"])
        if src.exists():
            raise FileOpError(f"Can't move back: {src} exists again.")
        if not dst.exists():
            raise FileOpError(f"Can't move back: {dst} is gone.")
        shutil.move(str(dst), str(src))
        _reindex_moved(dst, src)
        msg = f"Moved back to {src}"
    else:
        if not dst.exists():
            raise FileOpError(f"{dst} is already gone.")
        if entry["op"] == "create_folder" and dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir()
            msg = f"Removed the empty folder {dst}"
        else:
            _trash(dst)
            msg = f"Sent {dst} to the Trash"
    for e in entries:
        if e["id"] == action_id:
            e["undone"] = True
    _log_file().write_text("".join(json.dumps(e) + "\n" for e in entries))
    return msg


def _trash(p: Path):
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", str(p)], capture_output=True, text=True)
        if r.returncode == 0:
            return
        raise FileOpError(f"Couldn't move {p} to the Trash: {r.stderr.strip()}")
    raise FileOpError("No Trash available here (gio missing); not removing anything.")


def _reindex_moved(src: Path, dst: Path):
    """Keep search results (and their descriptions, transcripts, passages) for moved files."""
    import re

    from . import index

    conn = index.connect()
    try:
        rows = conn.execute(
            "SELECT id, path FROM files WHERE path = ? OR path LIKE ?", (str(src), str(src) + os.sep + "%")
        ).fetchall()
        for r in rows:
            new = Path(str(dst) + r["path"][len(str(src)):])
            if not any(new == root or new.is_relative_to(root) for root in settings.roots):
                continue
            words = lambda s: " ".join(re.findall(r"[^\W_]+", s))
            conn.execute("UPDATE files SET path=?, name=?, ext=? WHERE id=?",
                         (str(new), new.name, new.suffix.lower().lstrip("."), r["id"]))
            conn.execute("UPDATE files_fts SET name=?, path=? WHERE rowid=?", (words(new.stem), words(str(new.parent)), r["id"]))
        conn.commit()
    finally:
        conn.close()
