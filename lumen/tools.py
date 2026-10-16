"""Tools the Finder agent can call. All of them are limited to the indexed folders."""

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

from langchain_core.tools import tool
from langgraph.types import interrupt

from .search import images, passages
from .search import text as text_search
from .indexing.extract import extract_text
from .core.filetypes import IMAGE_EXTS, MEDIA_EXTS, RUNNABLE_EXTS
from .core.formatting import fmt_time
from .core.settings import settings
from .storage import catalog, db

def _allowed(p: str) -> Path:
    path = Path(p).expanduser().resolve()
    if not any(path == r or path.is_relative_to(r) for r in settings.roots):
        raise PermissionError(f"{path} is outside the allowed folders: {', '.join(map(str, settings.roots))}")
    return path


def _launch(target: Path, start: float = 0) -> str:
    cmd = ["xdg-open", str(target)]
    at = ""
    if start > 0 and settings.open_mode != "xdg":
        at = f" in the video player at {fmt_time(start)}"
    elif start > 0:
        at = f" at {fmt_time(start)}"
        if shutil.which("mpv"):
            cmd = ["mpv", "--force-window", f"--start={int(start)}", str(target)]
        elif shutil.which("vlc"):
            cmd = ["vlc", f"--start-time={int(start)}", str(target)]
        else:
            at = f" (no mpv/vlc to jump to {fmt_time(start)}; opened from the start)"
    if settings.open_mode != "xdg":
        return (
            f"NOT OPENED (test mode: running in Docker without a desktop). Would have opened: {target}{at}. "
            "Tell the user it was not opened and give the full path."
        )
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return f"Opened: {target}{at}"


def image_hits(conn, scored: list[tuple[dict, float]]) -> list[dict]:
    """Result-card dicts for visual matches, with each image's AI description as the snippet."""
    out = []
    for r, score in scored:
        row = conn.execute("SELECT caption FROM files WHERE path=?", (r["path"],)).fetchone()
        caption = (row["caption"] if row else "") or ""
        hit = text_search.Hit(r["path"], r["name"], r["ext"], r["size"], r["mtime"], caption[:200]).to_dict()
        hit["score"] = round(score, 3)
        out.append(hit)
    return out


def hybrid_image_search(conn, description: str, limit: int = 8, folder: str = "") -> list[dict]:
    """Images matching a description: what they look like (CLIP) fused with their AI description (text)."""
    by_look = images.search_text(conn, description, k=limit * 2, folder=folder)
    by_text = text_search.search(description, ext=",".join(sorted(IMAGE_EXTS)), folder=folder, limit=limit * 2)
    score, info = {}, {}
    for rank, (r, s) in enumerate(by_look):  # reciprocal rank fusion
        score[r["path"]] = score.get(r["path"], 0) + 1 / (10 + rank)
        info[r["path"]] = (r, s)
    for rank, h in enumerate(by_text):
        if h.partial:
            continue
        score[h.path] = score.get(h.path, 0) + 1 / (10 + rank)
        info.setdefault(h.path, ({"path": h.path, "name": h.name, "ext": h.ext, "size": h.size, "mtime": h.mtime}, 0.0))
    best = sorted(score, key=lambda p: -score[p])[:limit]
    return image_hits(conn, [info[p] for p in best])


def make_tools(emit=None, app=False, state=None):
    """Build the tool set for one chat session.

    `last_results` remembers the latest search so "open the second one" or
    "show me that file" can be resolved to a real path. `emit(event)` receives
    structured results (for UI cards) next to the text the model sees.
    """
    # shared with the API so results shown by app buttons (e.g. "Find similar") count as "the last results"
    last_results: list[str] = (state if state is not None else {}).setdefault("last_results", [])
    emit = emit or (lambda event: None)

    def resolve(target: str) -> Path:
        t = target.strip().lstrip("#")
        if t.isdigit():
            n = int(t)
            if not last_results:
                raise ValueError("No previous search results. Search first.")
            if not 1 <= n <= len(last_results):
                raise ValueError(f"Result number must be between 1 and {len(last_results)}.")
            return _allowed(last_results[n - 1])
        path = _allowed(target)
        if not path.exists() and "%" in target:
            path = _allowed(unquote(target))  # model sent a URL-encoded path ("%20" for spaces)
        return path

    @tool
    def search_files(
        query: str = "",
        ext: str = "",
        modified_after: str = "",
        modified_before: str = "",
        folder: str = "",
        limit: int = 8,
        min_minutes: float = 0,
        max_minutes: float = 0,
    ) -> str:
        """Full-text search over the user's files: names, folders, text inside documents,
        AI descriptions of images/videos and what is said in videos/audio.

        Args:
            query: keywords to look for, e.g. "invoice ali". Leave empty to list files by filters only.
            ext: file extensions to keep, comma separated, e.g. "pdf" or "pdf,docx". Empty = any type.
            modified_after: only files modified on/after this date, YYYY-MM-DD.
            modified_before: only files modified on/before this date, YYYY-MM-DD.
            folder: only files whose path contains this text, e.g. "Downloads".
            limit: max results (default 8).
            min_minutes: ONLY if the user asks about length ("longer than 30 minutes"); otherwise leave 0.
            max_minutes: ONLY if the user asks about length ("shorter than 5 minutes"); otherwise leave 0.
        """
        hits = text_search.search(
            query, ext, modified_after, modified_before, folder, min(max(limit, 1), 20), min_minutes, max_minutes
        )
        last_results[:] = [h.path for h in hits]
        emit({"type": "results", "hits": [h.to_dict() for h in hits]})
        if not hits:
            return "No files found. Try fewer or different words (synonyms), or remove filters."
        listing = "\n".join(h.line(i) for i, h in enumerate(hits, 1))
        if hits[0].partial:
            listing = ("NO EXACT MATCH: no file contains all the words. These are only partial matches; "
                       "tell the user what is missing and do not open them unless asked.\n" + listing)
        if app:
            # Small models follow the latest text best: remind them here, not only in the system prompt
            listing += ("\n\n(The user already sees these results as cards. Do not list them again: "
                        "answer in 1-2 short sentences and name only the best match.)")
        return listing

    @tool
    def read_file(target: str, question: str = "", max_chars: int = 4000) -> str:
        """Read a file to answer a question about its contents. Long files: pass the user's question
        and you get the parts of the file most relevant to it (plus the beginning).

        Args:
            target: full file path, or a result number from the last search (e.g. "1").
            question: what the user wants to know, e.g. "where did I work in 2014".
            max_chars: how much text to return (default 4000).
        """
        path = resolve(target)
        ext = path.suffix.lower().lstrip(".")
        budget = min(max(max_chars, 2000), 6000)  # small models sometimes ask for 500 chars and miss the answer
        text = extract_text(path, ext, path.stat().st_size)
        what = ""
        if not text.strip():
            text = catalog.indexed_text(str(path))
            if not text:
                return f"{path.name}: no readable text (binary, scanned or unsupported file)."
            what = " (metadata, description and transcript)" if ext in MEDIA_EXTS else " (AI description)"
        if len(text) <= budget:
            return f"--- {path}{what}: complete, {len(text):,} characters ---\n{text}"
        if question.strip():
            parts, total = passages.best_parts(text, question, budget)
            shown = ", ".join(str(i + 1) for i, _ in parts)
            body = "\n[...]\n".join(f"[part {i + 1}/{total}]\n{p}" for i, p in parts)
            out = (
                f"--- {path}{what}: {len(text):,} characters in {total} parts; showing the parts most relevant "
                f"to the question ({shown}). Other parts were NOT read: do not claim something is missing "
                f"from this file. ---\n{body}"
            )
            if not passages.best_parts.matched:
                out += "\n\n=== This file has nothing matching the question. Best passages in OTHER files: ===\n"
                out += _other_files(question, path)
            return out
        return (
            f"--- {path}{what}: showing the first {budget:,} of {len(text):,} characters. The rest was NOT read: "
            f"to answer a question, call read_file again with question=..., or use find_in_files. ---\n{text[:budget]}"
        )

    def _other_files(question: str, skip: Path) -> str:
        conn = db.connect()
        try:
            found = [r for r in passages.search(conn, question, limit=4, relevance_sql=text_search.RELEVANCE_SQL) if r["path"] != str(skip)]
        finally:
            conn.close()
        return "\n\n".join(f"{r['name']}  path: {r['path']}\n{r['text']}" for r in found[:3]) or "(none)"

    @tool
    def find_in_files(question: str, folder: str = "", ext: str = "") -> str:
        """Search INSIDE all documents, images, scans and videos for the passages that answer a question
        about facts: dates, jobs, places, amounts, names, ID numbers ("where did I work in 2014?",
        "how much tax was deducted in March?"). Returns the matching passages and their files.

        Args:
            question: the user's question in their words.
            folder: only files whose path contains this text (optional).
            ext: only these file types, comma separated (optional).
        """
        conn = db.connect()
        try:
            found = passages.search(conn, question, limit=6, folder=folder, ext=ext, relevance_sql=text_search.RELEVANCE_SQL)
        finally:
            conn.close()
        if not found:
            return "No passage matches. Try other words, or search_files to find the file by name."
        files = list(dict.fromkeys(r["path"] for r in found))
        last_results[:] = files
        best = {}  # best passage per file, in rank order: shown as result cards in the app
        for r in found:
            best.setdefault(r["path"], r)
        emit({"type": "results", "hits": [
            text_search.Hit(r["path"], r["name"], r["ext"], r["size"], r["mtime"], " ".join(r["text"].split())[:220],
                      r["duration"]).to_dict()
            for r in best.values()
        ]})
        out = []
        for r in found:
            n = files.index(r["path"]) + 1
            out.append(f"[{n}] {r['name']} (part {r['idx'] + 1}/{r['total']})  path: {r['path']}\n{r['text']}")
        return (
            "Passages from your files, best first. Answer ONLY from these and name the file you used. "
            "Several files can say different things (older and newer versions): prefer the most specific passage.\n\n"
            + "\n\n".join(out)
        )

    @tool
    def list_dir(path: str) -> str:
        """List what is inside a folder.

        Args:
            path: full folder path.
        """
        folder = _allowed(path)
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
                + _launch(path.parent)
            )
        start = start_seconds if ext in MEDIA_EXTS else 0
        result = _launch(path, start)
        emit({"type": "opened", "path": str(path), "start_seconds": start, "dry_run": settings.open_mode != "xdg"})
        return result

    @tool
    def show_in_folder(target: str) -> str:
        """Open the folder that contains a file in the file manager.

        Args:
            target: full file path, or a result number from the last search (e.g. "1").
        """
        path = resolve(target)
        return _launch(path if path.is_dir() else path.parent)

    @tool
    def search_images(description: str, folder: str = "") -> str:
        """Find photos/images by what they SHOW, e.g. "sunset at the beach", "my passport", "a red car",
        "screenshots of code". Matches how images look, not only file names.

        Args:
            description: what is in the picture.
            folder: only images whose path contains this text (optional).
        """
        conn = db.connect()
        try:
            hits = hybrid_image_search(conn, description, folder=folder)
        finally:
            conn.close()
        last_results[:] = [h["path"] for h in hits]
        emit({"type": "results", "hits": hits})
        if not hits:
            return "No matching images."
        return "\n".join(f"{i}. {h['name']}  path: {h['path']}\n   shows: {h['snippet'][:160]}" for i, h in enumerate(hits, 1))

    @tool
    def find_similar_images(target: str) -> str:
        """Find images that look like a given image (same scene, person, document type...).

        Args:
            target: full image path, or a result number from the last results (e.g. "1").
        """
        path = resolve(target)
        conn = db.connect()
        try:
            hits = image_hits(conn, images.similar_to(conn, str(path)))
        finally:
            conn.close()
        last_results[:] = [h["path"] for h in hits]
        emit({"type": "results", "hits": hits})
        if not hits:
            return f"No images look like {path.name}."
        return f"Images that look like {path.name}:\n" + "\n".join(
            f"{i}. {h['name']}  path: {h['path']}  similarity {h['score']}" for i, h in enumerate(hits, 1))

    # ---- changes: each one pauses for the user's approval (LangGraph interrupt) ----

    def _approved(plan: dict) -> str:
        """Ask the user, then do it. Re-running after resume repeats the checks, not the change."""
        from . import fileops

        decision = interrupt({"type": "approval", **{k: v for k, v in plan.items() if k != "content"}})
        if not (decision or {}).get("approved"):
            emit({"type": "action_cancelled", "summary": plan["summary"]})
            return (f"CANCELLED by the user: {plan['summary']}. Nothing changed. Tell the user it was cancelled; "
                    "do not ask them to approve it again.")
        try:
            done = fileops.execute(plan)
        except (fileops.FileOpError, OSError) as e:
            emit({"type": "action_failed", "summary": plan["summary"], "error": str(e)})
            return f"Failed: {e}"
        emit({"type": "action_done", **{k: v for k, v in done.items() if k != "content"}})
        if done.get("dst"):
            last_results[:] = [done["dst"]]
        return done["message"]

    def _plan(fn, *args) -> str:
        from . import fileops

        try:
            return _approved(fn(*args))
        except fileops.FileOpError as e:
            return f"Can't do that: {e}"

    @tool
    def create_folder(path: str) -> str:
        """Create a new folder (asks the user to approve first).

        Args:
            path: full path of the new folder, inside the user's folders, e.g. "~/Documents/Taxes 2026".
        """
        from . import fileops

        return _plan(fileops.plan_create_folder, path)

    @tool
    def create_file(path: str, content: str) -> str:
        """Create a new small TEXT file with the given content (asks the user to approve first).
        Never overwrites an existing file.

        Args:
            path: full path of the new file, e.g. "~/Documents/notes/todo.txt".
            content: the text to write.
        """
        from . import fileops

        return _plan(fileops.plan_create_file, path, content)

    @tool
    def copy_file(source: str, destination: str) -> str:
        """Copy a file or a whole folder (asks the user to approve first). Never overwrites.

        Args:
            source: full path, or a result number from the last results (e.g. "1").
            destination: a folder to copy into, or the full new path.
        """
        from . import fileops

        return _plan(fileops.plan_copy, str(resolve(source)), destination)

    @tool
    def move_file(source: str, destination: str) -> str:
        """Move or rename a file or folder (asks the user to approve first). Never overwrites.
        To rename, give the same folder with the new name.

        Args:
            source: full path, or a result number from the last results (e.g. "1").
            destination: a folder to move into, or the full new path (new name).
        """
        from . import fileops

        return _plan(fileops.plan_move, str(resolve(source)), destination)

    return [search_files, find_in_files, read_file, search_images, find_similar_images, list_dir,
            open_file, show_in_folder, create_folder, create_file, copy_file, move_file]
