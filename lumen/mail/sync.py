"""Reading mailboxes in the background: a thread in `lumen serve` reads new mail from every account
every few minutes (and at once on "Sync now") and indexes it. Read-only: nothing in a mailbox changes."""

import logging
import threading
import time

from . import accounts, store
from .imap import Mailbox
from .parse import parse

log = logging.getLogger(__name__)

EVERY = 10 * 60  # seconds between syncs


class MailSync:
    def __init__(self, every: float = EVERY) -> None:
        self.every = every
        self.status: dict[str, dict] = {}  # account id -> {state, last, error, folder, new}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mail-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def sync_soon(self) -> None:
        """Sync now (a new account, or "Sync now")."""
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            for account in accounts.all_accounts():
                if self._stop.is_set():
                    break
                self.sync_account(account)
            self._wake.wait(self.every)
            self._wake.clear()

    def sync_account(self, account: dict) -> int:
        """Read and index the account's new mail; returns how many mails were added."""
        aid = account["id"]
        with self._busy:
            self.status[aid] = {**self.status.get(aid, {}), "state": "syncing", "error": None}
            added = 0
            box = None
            try:
                box = Mailbox(account, accounts.secret(aid))
                db = store.mail_store()
                for folder in box.folders():
                    if self._stop.is_set():
                        break
                    self.status[aid]["folder"] = folder
                    validity = box.open(folder)
                    known, last = db.folder_state(aid, folder)
                    if known and known != validity:  # the server renumbered this folder
                        db.forget_folder(aid, folder)
                        last = 0
                    uids = box.new_uids(last, account.get("since_days", 365))
                    for uid, raw, size in box.fetch(uids):
                        m = parse(raw)
                        if not db.has_message(aid, m["message_id"]):
                            added += bool(db.add(aid, folder, validity, uid, size, m))
                        last = max(last, uid)
                        db.set_folder_state(aid, folder, validity, last)
                    if not uids:
                        db.set_folder_state(aid, folder, validity, last)
                self.status[aid] = {"state": "ok", "last": time.time(), "error": None, "new": added}
                log.info("mail %s: %d new", account["email"], added)
            except Exception as e:  # unreachable, password changed...: shown in the app, tried again later
                log.warning("mail %s: %s", account["email"], e)
                error = getattr(e, "message", str(e))
                self.status[aid] = {**self.status.get(aid, {}), "state": "error", "error": error}
            finally:
                if box:
                    box.close()
            return added

    def running(self) -> bool:
        return self._busy.locked()
