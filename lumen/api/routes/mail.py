"""Mailboxes: connecting (only from the laptop), their sync status, and reading an indexed mail and
its attachments. Read-only: nothing in a mailbox is ever changed."""

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends

from ...core import errors
from ...core.settings import settings
from ...mail import accounts
from ...mail import search as mail_search
from ...mail.imap import Mailbox
from ...mail.parse import attachment
from ...mail.store import mail_store
from ...viewer import kinds
from ..deps import auth, local_only, services
from ..responses import Deleted, MailAccountOut, MailOut, Ok
from ..schemas import MailAccountIn
from ..services import Services

router = APIRouter(dependencies=[Depends(auth)])


def cache_dir() -> Path:
    """Attachments opened in the viewer, fetched from the mail server (removed with the account)."""
    return settings.data_dir / "mail-cache"


def _out(account: dict, svc: Services) -> MailAccountOut:
    status = svc.mail.status.get(account["id"], {})
    return MailAccountOut.model_validate({**account, **status, "mails": mail_store().count(account["id"])})


@router.get("/api/mail/guess")
def guess(email: str) -> dict:
    """Server settings for an address, to fill in the form."""
    return accounts.guess(email)


@router.get("/api/mail/accounts")
def list_accounts(svc: Services = Depends(services)) -> list[MailAccountOut]:
    return [_out(a, svc) for a in accounts.all_accounts()]


@router.post("/api/mail/accounts", dependencies=[Depends(local_only)])
def add_account(body: MailAccountIn, svc: Services = Depends(services)) -> MailAccountOut:
    """Sign in and list the folders first (a wrong password is said now, not at the first sync)."""
    email = body.email.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise errors.InvalidInput("That isn't an email address.")
    guessed = accounts.guess(email)
    account = {
        "email": email,
        "host": body.host.strip() or guessed["host"],
        "port": body.port or guessed["port"],
        "security": body.security or guessed["security"],
        "user": body.user.strip() or email,
        "hint": guessed["hint"],
    }
    if account["security"] not in accounts.SECURITY:
        raise errors.InvalidInput(f"Security must be one of {', '.join(accounts.SECURITY)}.")
    secret = {"password": body.password}
    box = Mailbox(account, secret)
    try:
        box.folders()
    finally:
        box.close()
    saved = accounts.add(
        email, account["host"], account["port"], account["security"], account["user"], body.since_days, secret
    )
    svc.mail.sync_soon()
    return _out(saved, svc)


@router.delete("/api/mail/accounts/{account_id}", dependencies=[Depends(local_only)])
def remove_account(account_id: str) -> Deleted:
    """Forget a mailbox: its sign-in, its indexed mail and opened attachments. The mailbox itself is
    not touched."""
    account = accounts.remove(account_id)
    mail_store().forget_account(account_id)
    shutil.rmtree(cache_dir() / account_id, ignore_errors=True)
    return Deleted(deleted=account["email"])


@router.post("/api/mail/sync")
def sync_now(svc: Services = Depends(services)) -> Ok:
    svc.mail.sync_soon()
    return Ok()


def _mail(mail_id: int) -> dict:
    m = mail_store().get(mail_id)
    if m is None:
        raise errors.NotFound("That mail isn't indexed (its account was removed).")
    return m


@router.get("/api/mail/messages/{mail_id}")
def get_mail(mail_id: int) -> MailOut:
    m = _mail(mail_id)
    return MailOut.model_validate({**m, "path": f"{mail_search.PREFIX}{mail_id}", "text": m["body"] or ""})


@router.get("/api/mail/messages/{mail_id}/attachments/{idx}")
def open_attachment(mail_id: int, idx: int) -> dict:
    """Fetch an attachment from the mail server (read-only) into the cache and describe it for the
    viewer, which then shows it like a file (its "path")."""
    m = _mail(mail_id)
    info = next((a for a in m["attachments"] if a["idx"] == idx), None)
    if info is None:
        raise errors.NotFound("No such attachment.")
    folder = cache_dir() / m["account"] / f"{mail_id}-{idx}"
    name = Path(info["name"]).name.strip().lstrip(".") or f"attachment-{idx + 1}"
    path = folder / name
    if not path.is_file():
        box = Mailbox(accounts.get(m["account"]), accounts.secret(m["account"]))
        try:
            raw = box.fetch_one(m["folder"], m["uid"])
        finally:
            box.close()
        _, data = attachment(raw, idx)
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
    return kinds.describe(path)
