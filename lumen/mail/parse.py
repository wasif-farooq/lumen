"""A mail as Lumen keeps it: who, when, the subject, the text (HTML as text, quoted replies left
out) and its attachments, with the text of those Lumen can read (the same readers as files)."""

import email
import email.policy
import email.utils
import re
import tempfile
from collections.abc import Iterator
from email.message import EmailMessage, Message
from html.parser import HTMLParser
from pathlib import Path

from ..core.settings import settings
from ..indexing.extract import extract_text, extractor_for

MAX_TEXT = 1_000_000  # characters of a mail's own text kept
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # bigger attachments are listed, not read
MAX_ATTACHMENTS_TEXT = 2_000_000


def parse(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(msg, EmailMessage)
    name, addr = email.utils.parseaddr(str(msg.get("From", "")))
    try:
        date = email.utils.parsedate_to_datetime(str(msg.get("Date"))).timestamp()
    except (TypeError, ValueError, IndexError):
        date = 0.0
    recipients = ", ".join(a for _, a in email.utils.getaddresses([str(msg.get(h, "")) for h in ("To", "Cc")]) if a)
    attachments, texts = [], []
    for i, part in enumerate(_attachments(msg)):
        filename = part.get_filename() or f"attachment-{i + 1}"
        payload = _payload(part)
        info = {"idx": i, "name": filename, "type": part.get_content_type(), "size": len(payload), "has_text": False}
        text = _attachment_text(filename, payload)
        if text:
            info["has_text"] = True
            texts.append(f"{filename}:\n{text}")
        attachments.append(info)
    return {
        "message_id": str(msg.get("Message-ID", "")).strip(),
        "sender": addr.lower(),
        "sender_name": name or addr,
        "recipients": recipients,
        "subject": str(msg.get("Subject", "") or "(no subject)").strip(),
        "date": date,
        "text": body_text(msg)[:MAX_TEXT],
        "attachments": attachments,
        "attachments_text": "\n\n".join(texts)[:MAX_ATTACHMENTS_TEXT],
        "unsubscribe": bool(msg.get("List-Unsubscribe")),
    }


def body_text(msg: EmailMessage) -> str:
    """The mail's own words: plain text if there is some, else the HTML as text; quoted replies cut."""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):  # an unknown charset
        content = _payload(part).decode("utf-8", errors="replace")
    text = html_to_text(content) if part.get_content_type() == "text/html" else str(content)
    return trim_quotes(text)


def trim_quotes(text: str) -> str:
    """Leave out what the reply quotes ("> ..." lines and everything after "On ... wrote:")."""
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        if re.match(r"^\s*On .{5,200} wrote:\s*$", line) or re.match(r"^-{2,}\s*Original Message\s*-{2,}", line, re.I):
            break
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _attachments(msg: EmailMessage) -> Iterator[EmailMessage]:
    for part in msg.iter_attachments():
        if not isinstance(part, EmailMessage) or part.get_content_maintype() == "multipart":
            continue
        yield part


def _payload(part: Message) -> bytes:
    data = part.get_payload(decode=True)
    return data if isinstance(data, bytes) else b""


def attachment(raw: bytes, idx: int) -> tuple[str, bytes]:
    """One attachment of a message: its file name and bytes."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(msg, EmailMessage)
    for i, part in enumerate(_attachments(msg)):
        if i == idx:
            return part.get_filename() or f"attachment-{i + 1}", _payload(part)
    raise IndexError(idx)


def _attachment_text(filename: str, payload: bytes) -> str:
    """The text of an attachment Lumen can read (PDF, Word, Excel...), read from a file that is
    deleted right away: attachments aren't kept."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if not payload or len(payload) > MAX_ATTACHMENT_BYTES or extractor_for(ext) is None:
        return ""
    tmp_dir = settings.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=f".{ext}") as f:
        f.write(payload)
        f.flush()
        return extract_text(Path(f.name), ext, len(payload))


class _Text(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head", "title") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "tr", "table"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()
