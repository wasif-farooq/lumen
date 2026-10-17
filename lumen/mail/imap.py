"""Reading a mailbox over IMAP, read-only: folders are opened with EXAMINE and mail is read with
BODY.PEEK, so nothing in the mailbox changes, not even which mail is marked as read."""

import base64
import contextlib
import imaplib
import re
import ssl
from collections.abc import Iterator
from datetime import datetime, timedelta

from ..core import errors

TIMEOUT = 30
BATCH = 25  # messages fetched per request
MAX_MESSAGE_BYTES = 40 * 1024 * 1024  # bigger messages: headers only (the attachment isn't read)

# Folders never indexed: by their special-use flag, or (servers without flags) by name
SKIP_FLAGS = {"\\trash", "\\junk", "\\drafts", "\\all", "\\flagged", "\\important", "\\noselect"}
SKIP_NAMES = re.compile(r"(^|/|\.)(trash|deleted( items| messages)?|spam|junk( e-?mail)?|drafts?|bin)$", re.IGNORECASE)
_LIST = re.compile(r'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)')


class Mailbox:
    """One connection to one account."""

    def __init__(self, account: dict, secret: dict) -> None:
        self.account = account
        try:
            host, port, security = account["host"], int(account["port"]), account["security"]
            if security == "ssl":
                self.conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(),
                                                             timeout=TIMEOUT)  # fmt: skip
            else:
                self.conn = imaplib.IMAP4(host, port, timeout=TIMEOUT)
                if security == "starttls":
                    self.conn.starttls(ssl_context=ssl.create_default_context())
        except (OSError, imaplib.IMAP4.error) as e:
            raise errors.InvalidInput(f"Can't reach {account['host']}:{account['port']}: {e}",
                                      "Check the server name and port.") from e  # fmt: skip
        try:
            if secret.get("access_token"):  # Sign in with Google / Microsoft
                auth = f"user={account['user']}\x01auth=Bearer {secret['access_token']}\x01\x01"
                self.conn.authenticate("XOAUTH2", lambda _: auth.encode())
            else:
                self.conn.login(account["user"], secret.get("password", ""))
        except imaplib.IMAP4.error as e:
            self.close()
            hint = account.get("hint") or "Check the address and the (app) password."
            raise errors.InvalidInput(f"The mail server didn't accept the sign-in: {_text(e)}", hint) from e

    def close(self) -> None:
        with contextlib.suppress(Exception):  # already gone
            self.conn.logout()

    def folders(self) -> list[str]:
        """Folders worth indexing (not Trash, Spam, Drafts, or Gmail's "All Mail" copy of everything)."""
        typ, lines = self.conn.list()
        if typ != "OK":
            return ["INBOX"]
        out = []
        for raw in lines:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            m = _LIST.match(line)
            if not m:
                continue
            flags = {f.lower() for f in m.group("flags").split()}
            name = m.group("name").strip()
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('\\"', '"')
            if flags & SKIP_FLAGS or SKIP_NAMES.search(_decode_utf7(name)):
                continue
            out.append(name)
        return sorted(out, key=lambda n: (n.upper() != "INBOX", n.lower()))

    def open(self, folder: str) -> int:
        """Open a folder read-only (EXAMINE); its UIDVALIDITY (UIDs restart when it changes)."""
        typ, _ = self.conn.select(_quote(folder), readonly=True)
        if typ != "OK":
            raise errors.NotFound(f"Folder {folder} can't be opened.")
        validity = self.conn.response("UIDVALIDITY")[1]
        return int(validity[0]) if validity and validity[0] else 0

    def new_uids(self, after_uid: int, since_days: int) -> list[int]:
        """UIDs of mail after `after_uid`, or (the first time) from the last `since_days` days."""
        if after_uid:
            typ, data = self.conn.uid("SEARCH", f"UID {after_uid + 1}:*")
        else:
            since = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            typ, data = self.conn.uid("SEARCH", f"SINCE {since}")
        if typ != "OK" or not data or not data[0]:
            return []
        return sorted(u for u in (int(x) for x in data[0].split()) if u > after_uid)  # "N:*" can return N-1

    def fetch(self, uids: list[int]) -> Iterator[tuple[int, bytes, int]]:
        """(uid, the message, its size) for each UID, read without marking anything as read."""
        for start in range(0, len(uids), BATCH):
            batch = ",".join(str(u) for u in uids[start : start + BATCH])
            typ, data = self.conn.uid("FETCH", batch, "(RFC822.SIZE)")
            sizes = {}
            for item in data or []:
                line = item.decode() if isinstance(item, bytes) else ""
                if m := re.search(r"UID (\d+).*RFC822\.SIZE (\d+)|RFC822\.SIZE (\d+).*UID (\d+)", line):
                    uid, size = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                    sizes[int(uid)] = int(size)
            whole = [u for u in uids[start : start + BATCH] if sizes.get(u, 0) <= MAX_MESSAGE_BYTES]
            for part, uid_list in (("BODY.PEEK[]", whole), ("BODY.PEEK[HEADER]", [u for u in sizes if u not in whole])):
                if not uid_list:
                    continue
                typ, data = self.conn.uid("FETCH", ",".join(map(str, uid_list)), f"(UID {part})")
                for item in data or []:
                    if isinstance(item, tuple) and len(item) == 2:
                        m = re.search(rb"UID (\d+)", item[0])
                        if m:
                            uid = int(m.group(1))
                            yield uid, item[1], sizes.get(uid, len(item[1]))

    def fetch_one(self, folder: str, uid: int) -> bytes:
        """One whole message (opening an attachment)."""
        self.open(folder)
        typ, data = self.conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        for item in data or []:
            if isinstance(item, tuple) and len(item) == 2:
                return item[1]
        raise errors.NotFound("That mail is no longer in the mailbox.")


def _quote(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _text(e: Exception) -> str:
    s = str(e)
    return s[2:-1] if s.startswith("b'") else s


def _decode_utf7(name: str) -> str:
    """IMAP's modified UTF-7 folder names ("&AMk-t&AOk-" -> "Été"), for showing and matching."""

    def part(m: re.Match) -> str:
        if m.group(1) == "":
            return "&"
        b64 = m.group(1).replace(",", "/")
        b64 += "=" * (-len(b64) % 4)
        try:
            return base64.b64decode(b64).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return m.group(0)

    return re.sub(r"&([^-]*)-", part, name)


def folder_label(name: str) -> str:
    return _decode_utf7(name)
