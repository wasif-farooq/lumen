"""Mail accounts and indexed mail."""

from .common import Out


class MailAccountOut(Out):
    """A connected mailbox (never its password or tokens)."""

    id: str
    email: str
    host: str
    port: int
    security: str
    user: str
    since_days: int
    added: float
    mails: int = 0  # indexed so far
    state: str = "waiting"  # waiting, syncing, ok, error
    last: float | None = None  # last finished sync
    error: str | None = None
    folder: str | None = None  # being read now


class MailAttachmentOut(Out):
    idx: int
    name: str
    type: str
    size: int
    has_text: bool = False


class MailOut(Out):
    id: int
    path: str  # "mail:<id>"
    account: str
    folder: str
    sender: str
    sender_name: str
    recipients: str
    subject: str
    date: float
    text: str
    attachments: list[MailAttachmentOut]
