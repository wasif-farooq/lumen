"""Carrying out approved plans, and undoing them. Never deletes and never overwrites: undo moves
things back, or sends what was created or copied to the Trash."""

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from ..core.settings import settings
from . import journal
from .plans import FileOpError, plan_copy, plan_create_file, plan_create_folder, plan_move


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
    entry = {
        "id": uuid.uuid4().hex[:12],
        "at": time.time(),
        "op": op,
        "src": fresh.get("src"),
        "dst": str(dst),
        "summary": fresh["summary"],
        "undone": False,
    }
    journal.append(entry)
    return {**entry, "dry_run": False, "message": f"Done: {fresh['summary']}"}


def undo(action_id: str) -> str:
    """Reverse a logged change: move back, or send what was created/copied to the Trash (recoverable)."""
    entries = journal.history()
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
    journal.save(entries)
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
    from ..indexing.scan import words
    from ..storage import db

    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, path FROM files WHERE path = ? OR path LIKE ?", (str(src), str(src) + os.sep + "%")
        ).fetchall()
        for r in rows:
            new = Path(str(dst) + r["path"][len(str(src)) :])
            if not any(new == root or new.is_relative_to(root) for root in settings.roots):
                continue
            conn.execute(
                "UPDATE files SET path=?, name=?, ext=? WHERE id=?",
                (str(new), new.name, new.suffix.lower().lstrip("."), r["id"]),
            )
            conn.execute(
                "UPDATE files_fts SET name=?, path=? WHERE rowid=?", (words(new.stem), words(str(new.parent)), r["id"])
            )
        conn.commit()
    finally:
        conn.close()
