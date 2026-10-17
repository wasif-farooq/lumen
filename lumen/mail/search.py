"""Mail in search and chat: hits from the mail index (path "mail:<id>", kind "mail"), and mixing them
with file hits."""

import re
from datetime import datetime

from ..search.query import match_exprs, query_terms
from ..search.text import Hit
from .store import mail_store

PREFIX = "mail:"
# Words that make a search about mail: mail hits come first then
MAIL_WORDS = re.compile(r"\b(e-?mails?|mails?|inbox|sent me|wrote|message from|replied)\b", re.IGNORECASE)


def is_mail(path: str) -> bool:
    return path.startswith(PREFIX)


def mail_id(path: str) -> int:
    try:
        return int(path.removeprefix(PREFIX))
    except ValueError:
        return -1


def target(t: str, last_results: list[str]) -> str:
    """The mail path a read_file target means ("mail:12", or the number of a mail result), else ""."""
    t = t.strip().lstrip("#")
    if t.isdigit() and 1 <= int(t) <= len(last_results):
        t = last_results[int(t) - 1]
    return t if is_mail(t) else ""


def as_text(path: str) -> tuple[str, str]:
    """A mail as text for the chat model: (a header line, the headers, text and attachments' text)."""
    m = mail_store().get(mail_id(path))
    if m is None:
        raise ValueError("That mail is no longer indexed (its account was removed).")
    when = datetime.fromtimestamp(m["date"] or 0).strftime("%Y-%m-%d %H:%M")
    names = ", ".join(a["name"] for a in m["attachments"]) or "none"
    head = f'email "{m["subject"]}" from {m["sender_name"]} <{m["sender"]}>, {when}'
    body = f"From: {m['sender_name']} <{m['sender']}>\nTo: {m['recipients']}\nDate: {when}\n"
    body += f"Subject: {m['subject']}\nAttachments: {names}\n\n{m['body'] or ''}"
    if (m["attachments_text"] or "").strip():
        body += f"\n\n=== Attachments ===\n{m['attachments_text']}"
    return head, body


def search(query: str, limit: int = 10, after: str = "", before: str = "") -> list[Hit]:
    terms = query_terms(query)
    if not terms:
        return []
    where, params = [], []
    if after:
        where.append("m.date >= ?")
        params.append(datetime.strptime(after, "%Y-%m-%d").timestamp())
    if before:
        where.append("m.date < ?")
        params.append(datetime.strptime(before, "%Y-%m-%d").timestamp() + 86400)
    db = mail_store()
    for match, partial in match_exprs(terms):
        sql = (
            "SELECT m.*, snippet(mail_fts, -1, '[', ']', '…', 12) AS snip FROM mail_fts "
            "JOIN messages m ON m.id = mail_fts.rowid WHERE mail_fts MATCH ?"
            + "".join(" AND " + w for w in where)
            # the subject and people weigh most, then the text, then attachments; "kind" not at all
            + " ORDER BY bm25(mail_fts, 8.0, 5.0, 1.0, 0.7, 0.0) LIMIT ?"
        )
        try:
            rows = db.rows(sql, (match, *params, limit))
        except Exception:  # a query FTS can't read
            return []
        if rows:
            return [
                Hit(
                    f"{PREFIX}{r['id']}",
                    r["subject"] or "(no subject)",
                    "eml",
                    r["size"] or 0,
                    r["date"] or 0,
                    " ".join((r["snip"] or "").split()),
                    partial=partial,
                    kind="mail",
                    sender=r["sender_name"] or r["sender"] or "",
                )
                for r in rows
            ]
    return []


def mixed(files: list[Hit], mails: list[Hit], query: str, limit: int) -> list[Hit]:
    """Files and mail in one list: alternating, files first unless the search is about mail; a
    partial ("any word") match never comes before a full one."""
    first, second = (mails, files) if MAIL_WORDS.search(query) else (files, mails)
    first = [h for h in first if not h.partial] + [h for h in first if h.partial]
    out: list[Hit] = []
    for i in range(max(len(first), len(second))):
        for group in (first, second):
            if i < len(group):
                out.append(group[i])
    full = [h for h in out if not h.partial]
    return (full + [h for h in out if h.partial])[:limit]
