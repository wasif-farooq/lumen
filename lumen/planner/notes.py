"""Notes: Markdown files in the notes folder (by default "Lumen Notes" in the first indexed folder),
so they are the user's own files, open in any editor, and found by search like any other file.

    ---
    title: Plumber
    created: 2026-10-17 14:30
    updated: 2026-10-17 14:35
    tags: home, repairs
    ---

    Ahmed, 0300 1234567. Comes on Tuesdays.

Lumen writes here without asking each time (it is Lumen's own folder, and a spoken "note: ..."
shouldn't need a click), but every change is logged so it can be undone, and a deleted note goes
to the Trash. Notes written elsewhere (no frontmatter) work too: the title is the first heading or
the file name. Nothing outside this folder is touched.
"""

import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..core import errors
from ..core.settings import settings
from ..fileops import journal
from ..fileops.actions import _trash

TITLE_MAX = 80
BAD_NAME = re.compile(r'[\x00-\x1f/\\:*?"<>|]+')


def folder() -> Path:
    """The notes folder (made when the first note is saved)."""
    if settings.notes_dir:
        return Path(settings.notes_dir).expanduser().resolve()
    return settings.roots[0] / "Lumen Notes"


def list_notes(query: str = "") -> list[dict]:
    """Notes, most recently changed first; with a query, only those whose title or text has it."""
    base = folder()
    if not base.is_dir():
        return []
    out = []
    q = query.strip().lower()
    for path in base.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(base).parts):
            continue
        note = _read(path)
        if q and q not in note["title"].lower() and q not in note["text"].lower():
            continue
        out.append({**{k: v for k, v in note.items() if k != "text"}, "preview": _preview(note["text"])})
    return sorted(out, key=lambda n: n["updated"], reverse=True)


def get(name: str) -> dict:
    return _read(_path(name))


def find(title: str) -> dict | None:
    """A note by title (any case), or by file name."""
    want = title.strip().lower()
    for note in list_notes():
        if note["title"].lower() == want or Path(note["name"]).stem.lower() == want:
            return get(note["name"])
    return None


def create(title: str, text: str = "", tags: list[str] | None = None) -> dict:
    title = _clean_title(title)
    _writable()
    base = folder()
    base.mkdir(parents=True, exist_ok=True)
    path = _free_name(base, title)
    now = _stamp()
    with path.open("x", encoding="utf-8") as f:  # "x": never overwrite
        f.write(_compose(title, text, tags or [], now, now))
    action = _log("create_file", path, f"Created the note “{title}”")
    return {**_read(path), "action_id": action}


def append(name: str, text: str) -> dict:
    """Add text at the end of a note (a new paragraph)."""
    note = get(name)
    joined = (note["text"].rstrip() + "\n\n" + text.strip()).strip() + "\n"
    return update(name, text=joined)


def update(name: str, title: str | None = None, text: str | None = None, tags: list[str] | None = None) -> dict:
    """Change a note's text, tags or title (a new title renames the file too)."""
    _writable()
    path = _path(name)
    note = _read(path)
    backup = _backup(path)
    new_title = note["title"] if title is None else _clean_title(title)
    new_path = path
    if new_title != note["title"]:
        new_path = _free_name(path.parent, new_title, keep=path)
    content = _compose(
        new_title,
        note["text"] if text is None else text,
        note["tags"] if tags is None else tags,
        note["created"],
        _stamp(),
    )
    path.write_text(content, encoding="utf-8")
    if new_path != path:
        path.rename(new_path)
    action = _log("note_edit", new_path, f"Changed the note “{new_title}”", src=path, backup=backup)
    return {**_read(new_path), "action_id": action}


def trash(name: str) -> dict:
    """Send a note to the Trash (Undo puts it back)."""
    _writable()
    path = _path(name)
    note = _read(path)
    backup = _backup(path)
    _trash(path)
    action = _log("note_delete", path, f"Sent the note “{note['title']}” to the Trash", backup=backup)
    return {"name": note["name"], "title": note["title"], "action_id": action}


def undo(entry: dict) -> str:
    """Undo a note_edit or note_delete from the change log (fileops.undo calls this)."""
    dst, backup = Path(entry["dst"]), Path(entry["backup"])
    if not backup.is_file():
        raise errors.InvalidInput("The earlier version of this note is gone; can't undo.")
    if entry["op"] == "note_delete":
        if dst.exists():
            raise errors.Conflict(f"{dst.name} exists again; not replacing it.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, dst)
        return f"Put the note back: {dst.name}"
    src = Path(entry["src"])
    if not dst.exists():
        raise errors.Conflict(f"{dst.name} is gone; can't undo the change.")
    if src != dst:
        if src.exists():
            raise errors.Conflict(f"{src.name} exists again; can't rename back.")
        dst.rename(src)
    shutil.copy2(backup, src)
    return f"Put back the earlier version of {src.name}"


# ---------- the files ----------


def _path(name: str) -> Path:
    base = folder()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or path.suffix.lower() != ".md":
        raise errors.InvalidInput("Notes are .md files in the notes folder.")
    if not path.is_file():
        raise errors.NotFound(f"No note called {name}.")
    return path


def _read(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _split(raw)
    stat = path.stat()
    heading = re.match(r"\s*#\s+(.+)", body)
    title = meta.get("title") or (heading.group(1).strip() if heading else path.stem)
    return {
        "name": str(path.relative_to(folder())),
        "path": str(path),
        "title": title,
        "text": body,
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "created": meta.get("created") or _stamp(stat.st_ctime),
        "updated": meta.get("updated") or _stamp(stat.st_mtime),
    }


def _split(raw: str) -> tuple[dict, str]:
    """Frontmatter (simple `key: value` lines) and the Markdown body."""
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---", 4)
    if end < 0:
        return {}, raw
    meta = {}
    for line in raw[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    return meta, raw[end + 4 :].lstrip("\n")


def _compose(title: str, text: str, tags: list[str], created: str, updated: str) -> str:
    tags_line = ", ".join(t.strip() for t in tags if t.strip())
    head = f"---\ntitle: {title}\ncreated: {created}\nupdated: {updated}\ntags: {tags_line}\n---\n\n"
    return head + text.strip() + "\n"


def _clean_title(title: str) -> str:
    title = " ".join(title.split())[:TITLE_MAX].strip()
    if not title:
        raise errors.InvalidInput("A note needs a title.")
    return title


def _free_name(base: Path, title: str, keep: Path | None = None) -> Path:
    """ "Plumber.md", or "Plumber (2).md" when that is taken."""
    stem = BAD_NAME.sub(" ", title).strip(" .") or "Note"
    path, n = base / f"{stem}.md", 2
    while path.exists() and path != keep:
        path, n = base / f"{stem} ({n}).md", n + 1
    return path


def _preview(text: str, limit: int = 140) -> str:
    flat = " ".join(re.sub(r"[#*_`>]", " ", text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _stamp(t: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if t is None else t).strftime("%Y-%m-%d %H:%M")


def _writable() -> None:
    if not settings.write_enabled:
        raise errors.InvalidInput("Test mode: notes can't be saved here.")


def _backup(path: Path) -> Path:
    """Keep the note as it is now, so a change can be undone."""
    store = settings.data_dir / "note-history"
    store.mkdir(parents=True, exist_ok=True)
    copy = store / f"{uuid.uuid4().hex[:12]}.md"
    shutil.copy2(path, copy)
    return copy


def _log(op: str, dst: Path, summary: str, src: Path | None = None, backup: Path | None = None) -> str:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "at": time.time(),
        "op": op,
        "src": str(src) if src else None,
        "dst": str(dst),
        "summary": summary,
        "undone": False,
    }
    if backup:
        entry["backup"] = str(backup)
    journal.append(entry)
    return entry["id"]
