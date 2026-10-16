"""Finding files and the parts of files that answer a question."""

from pathlib import Path

from langchain_core.tools import tool

from ...core.filetypes import MEDIA_EXTS
from ...indexing.extract import extract_text
from ...search import passages
from ...search import text as text_search
from ...storage import catalog, db


def build(ctx) -> dict:
    last_results, emit, resolve, app = ctx.last_results, ctx.emit, ctx.resolve, ctx.app

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

    return {"search_files": search_files, "read_file": read_file, "find_in_files": find_in_files}
