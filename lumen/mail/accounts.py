"""Mail accounts: where each mailbox is (mail-accounts.json) and how to sign in (mail-secrets.json,
readable only by this user, never sent to the app)."""

import json
import time
import uuid
from pathlib import Path

from ..core import errors, private_files
from ..core.settings import settings

# IMAP servers of common providers, by the address's domain (anything else: imap.<domain>, port 993)
PROVIDERS = {
    "gmail.com": ("imap.gmail.com", "Gmail: use an app password (Google Account → Security → App passwords)."),
    "googlemail.com": ("imap.gmail.com", "Gmail: use an app password (Google Account → Security → App passwords)."),
    "yahoo.com": ("imap.mail.yahoo.com", "Yahoo: use an app password (Account security → Generate app password)."),
    "icloud.com": ("imap.mail.me.com", "iCloud: use an app-specific password (appleid.apple.com)."),
    "me.com": ("imap.mail.me.com", "iCloud: use an app-specific password (appleid.apple.com)."),
    "fastmail.com": ("imap.fastmail.com", "Fastmail: use an app password (Settings → Privacy & Security)."),
    "outlook.com": ("outlook.office365.com", "Outlook.com needs Sign in with Microsoft (passwords are turned off)."),
    "hotmail.com": ("outlook.office365.com", "Outlook.com needs Sign in with Microsoft (passwords are turned off)."),
    "live.com": ("outlook.office365.com", "Outlook.com needs Sign in with Microsoft (passwords are turned off)."),
}
SECURITY = ("ssl", "starttls", "none")  # none: only for a test server on this machine


def guess(email: str) -> dict:
    """Server settings for an address: known providers, else imap.<domain>:993 over SSL."""
    domain = email.rsplit("@", 1)[-1].strip().lower()
    host, hint = PROVIDERS.get(domain, (f"imap.{domain}", ""))
    return {"host": host, "port": 993, "security": "ssl", "hint": hint}


def _accounts_file() -> Path:
    return settings.data_dir / "mail-accounts.json"


def _secrets_file() -> Path:
    return settings.data_dir / "mail-secrets.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def all_accounts() -> list[dict]:
    return list(_read(_accounts_file()).get("accounts", []))


def get(account_id: str) -> dict:
    for a in all_accounts():
        if a["id"] == account_id:
            return a
    raise errors.NotFound("No such mail account.")


def secret(account_id: str) -> dict:
    return dict(_read(_secrets_file()).get(account_id, {}))


def add(email: str, host: str, port: int, security: str, user: str, since_days: int, secret_data: dict) -> dict:
    """Save an account (already checked by connecting) and its sign-in."""
    if security not in SECURITY:
        raise errors.InvalidInput(f"Security must be one of {', '.join(SECURITY)}.")
    accounts = all_accounts()
    if any(a["email"].lower() == email.lower() and a["host"] == host for a in accounts):
        raise errors.Conflict(f"{email} is already connected.")
    account = {
        "id": uuid.uuid4().hex[:10],
        "kind": "imap",
        "email": email,
        "host": host,
        "port": int(port),
        "security": security,
        "user": user or email,
        "since_days": max(1, min(int(since_days), 3650)),
        "added": time.time(),
    }
    private_files.write_json(_accounts_file(), {"accounts": [*accounts, account]})
    secrets = _read(_secrets_file())
    secrets[account["id"]] = secret_data
    private_files.write_json(_secrets_file(), secrets)
    return account


def update_secret(account_id: str, secret_data: dict) -> None:
    """New sign-in data (a refreshed token)."""
    secrets = _read(_secrets_file())
    secrets[account_id] = secret_data
    private_files.write_json(_secrets_file(), secrets)


def remove(account_id: str) -> dict:
    account = get(account_id)
    private_files.write_json(_accounts_file(), {"accounts": [a for a in all_accounts() if a["id"] != account_id]})
    secrets = _read(_secrets_file())
    secrets.pop(account_id, None)
    private_files.write_json(_secrets_file(), secrets)
    return account
