"""Mailboxes: connecting, indexing (text, HTML, attachments), finding mail next to files, reading
it in chat and the viewer, forgetting it, and never changing anything in the mailbox. Runs against
a real IMAP server (GreenMail) in Docker; skipped without Docker. All mail is made up."""

import imaplib
import json
import shutil
import subprocess
import time
import urllib.request
import uuid
from email.message import EmailMessage

import pymupdf
import pytest
from conftest import sse, sync_mail, tool_call
from langchain_core.messages import AIMessage, ToolMessage

IMAGE = "greenmail/standalone:2.1.3"


def _port(name: str, inner: int) -> int:
    out = subprocess.run(["docker", "port", name, str(inner)], capture_output=True, text=True, check=True)
    return int(out.stdout.splitlines()[0].rsplit(":", 1)[1])


@pytest.fixture(scope="module")
def greenmail():
    """An IMAP server on this machine: (imap port, user-API base URL)."""
    if not shutil.which("docker") or subprocess.run(["docker", "info"], capture_output=True).returncode:
        pytest.skip("Docker isn't available")
    name = f"lumen-test-mail-{uuid.uuid4().hex[:6]}"
    opts = "-Dgreenmail.setup.test.imap -Dgreenmail.hostname=0.0.0.0"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::3143", "-p", "127.0.0.1::8080",
         "-e", f"GREENMAIL_OPTS={opts}", IMAGE],
        capture_output=True, check=True,
    )  # fmt: skip
    try:
        imap, api = _port(name, 3143), f"http://127.0.0.1:{_port(name, 8080)}"
        end = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(f"{api}/api/user", timeout=2)
                imaplib.IMAP4("127.0.0.1", imap, timeout=2).logout()
                break
            except OSError:
                if time.time() > end:
                    raise
                time.sleep(0.5)
        yield imap, api
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


class Box:
    """A made-up mailbox on the test server, filled by the test (as another mail program would)."""

    def __init__(self, port: int, api: str) -> None:
        self.port, self.login, self.password = port, f"alex{uuid.uuid4().hex[:6]}", "garden-path-42"
        self.email = f"{self.login}@example.com"
        body = json.dumps({"email": self.email, "login": self.login, "password": self.password}).encode()
        req = urllib.request.Request(f"{api}/api/user", body, {"content-type": "application/json"})
        urllib.request.urlopen(req, timeout=10)

    def conn(self) -> imaplib.IMAP4:
        c = imaplib.IMAP4("127.0.0.1", self.port)
        c.login(self.login, self.password)
        return c

    def put(
        self, folder: str, subject: str, text: str = "", html: str = "", attachments: tuple = (), message_id: str = ""
    ) -> None:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = "Sam Rivera <sam@example.org>", self.email, subject
        m["Date"] = "Fri, 16 Oct 2026 09:30:00 +0000"
        m["Message-ID"] = message_id or f"<{uuid.uuid4().hex}@example.org>"
        m.set_content(text or "See below.")
        if html:
            m.add_alternative(html, subtype="html")
        for name, data, mime in attachments:
            main, sub = mime.split("/")
            m.add_attachment(data, maintype=main, subtype=sub, filename=name)
        c = self.conn()
        if folder != "INBOX":
            c.create(folder)
        c.append(folder, "", imaplib.Time2Internaldate(time.time()), m.as_bytes())
        c.logout()

    def flags(self, folder: str = "INBOX") -> list[bytes]:
        c = self.conn()
        c.select(folder, readonly=True)
        _, data = c.fetch("1:*", "(FLAGS)")
        c.logout()
        return [d for d in data if isinstance(d, bytes)]


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


@pytest.fixture
def box(greenmail) -> Box:
    return Box(*greenmail)


def connect(client, box: Box, password: str = ""):
    return client.post(
        "/api/mail/accounts",
        json={"email": box.email, "password": password or box.password, "host": "127.0.0.1", "port": box.port,
              "security": "none", "user": box.login, "since_days": 30},
    )  # fmt: skip


def search(client, q: str) -> list[dict]:
    return client.get("/api/search", params={"q": q}).json()


@pytest.fixture
def filled(env, local, box):
    """A mailbox with a statement (PDF attached), an HTML mail with a quoted reply, and mail in Trash
    and Spam, connected and read once."""
    statement = ("statement-oct.pdf", _pdf("Mooring invoice 7781 for the sailboat Petrel"), "application/pdf")
    box.put("INBOX", "Harbour berth statement", "Your berth fee for October is 120 EUR.", attachments=(statement,))
    shed = "The cedar shed goes behind the greenhouse."
    html = f"<html><head><style>p{{}}</style></head><body><p>{shed}</p></body></html>"
    box.put("Projects", "Garden shed plans", f"{shed}\n\nOn Mon, 12 Oct 2026, Pat wrote:\n> zucchini quote", html)
    box.put("Trash", "Old zeppelin tickets", "zeppelin")
    box.put("Junk", "Win a zeppelin", "zeppelin")
    r = connect(local, box)
    assert r.status_code == 200, r.text
    assert sync_mail(env) == 2
    return r.json()


def test_a_connected_mailbox_is_indexed_and_found_next_to_files(indexed, local, filled):
    [mail] = [h for h in search(local, "berth statement") if h["kind"] == "mail"]
    assert mail["path"].startswith("mail:") and mail["name"] == "Harbour berth statement"
    assert mail["sender"] == "Sam Rivera"
    assert [h["name"] for h in search(local, "mooring sailboat")] == ["Harbour berth statement"]  # the PDF's text
    assert [h["name"] for h in search(local, "cedar greenhouse")] == ["Garden shed plans"]  # other folders too
    assert search(local, "zucchini") == []  # the quoted reply isn't the mail's own text
    assert search(local, "zeppelin") == []  # Trash and Spam are left out
    assert search(local, "invoice")[0]["kind"] != "mail"  # files still come first...
    assert search(local, "emails about invoice")[0]["kind"] == "mail"  # ...unless the search is about mail
    assert all(h["kind"] != "mail" for h in local.get("/api/search", params={"q": "invoice", "ext": "pdf"}).json())

    [account] = local.get("/api/mail/accounts").json()
    assert account["mails"] == 2 and account["state"] == "ok" and account["email"] == filled["email"]


def test_reading_a_mailbox_changes_nothing_in_it(env, local, box, filled):
    assert not any(b"\\Seen" in f for f in box.flags())  # still unread in the user's mail program
    box.put("INBOX", "Library card renewal", "Renew the library card before November.")
    assert sync_mail(env) == 1  # only what is new
    assert sync_mail(env) == 0
    assert not any(b"\\Seen" in f for f in box.flags())


def test_the_same_mail_in_two_folders_is_indexed_once(env, local, box):
    for folder in ("INBOX", "Receipts"):
        box.put(folder, "Bicycle repair receipt", "Chain and brakes, 45 EUR", message_id="<bike-1@example.org>")
    assert connect(local, box).status_code == 200
    assert sync_mail(env) == 1


def test_secrets_stay_on_the_laptop(env, local, remote, box, filled):
    code = local.post("/api/pair/start").json()["code"]
    token = remote.post("/api/pair", json={"code": code, "name": "Alex's phone"}).json()["token"]
    remote.headers["Authorization"] = f"Bearer {token}"
    for r in (local.get("/api/mail/accounts"), remote.get("/api/mail/accounts")):
        assert r.status_code == 200 and box.password not in r.text
    secrets = env.data / "mail-secrets.json"
    assert secrets.stat().st_mode & 0o777 == 0o600
    assert connect(remote, box).status_code == 403  # a phone can't add mailboxes
    assert remote.delete(f"/api/mail/accounts/{filled['id']}").status_code == 403


def test_a_wrong_password_is_said_at_once_and_nothing_is_saved(env, local, box):
    r = connect(local, box, password="not-it")
    assert r.status_code == 400 and "sign-in" in r.json()["error"]["message"]
    assert local.get("/api/mail/accounts").json() == []
    assert not (env.data / "mail-secrets.json").exists()


def test_a_mail_and_its_attachment_open_in_the_viewer(env, local, filled):
    [hit] = [h for h in search(local, "berth") if h["kind"] == "mail"]
    mail_id = hit["path"].removeprefix("mail:")
    info = local.get("/api/view", params={"path": hit["path"]}).json()
    assert info["kind"] == "mail" and info["name"] == "Harbour berth statement"
    mail = local.get(f"/api/mail/messages/{mail_id}").json()
    assert "120 EUR" in mail["text"] and mail["sender"] == "sam@example.org"
    assert [a["name"] for a in mail["attachments"]] == ["statement-oct.pdf"]

    info = local.post(f"/api/mail/messages/{mail_id}/attachments/0").json()  # fetched from the server
    assert info["kind"] == "pdf" and info["pages"] == 1
    page = local.get("/api/view/page", params={"path": info["path"], "page": 0, "w": 400})
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert local.get("/api/view", params={"path": str(env.data / "mail.db")}).status_code == 403  # not the rest


def test_chat_finds_and_reads_a_mail(env, local, model, filled):
    model.script = [tool_call("search_files", query="berth statement"), tool_call("read_file", target="1"),
                    AIMessage(content="It is 120 EUR.")]  # fmt: skip
    chat = local.post("/api/chats", json={}).json()["id"]
    events = sse(local.post(f"/api/chats/{chat}/messages", json={"text": "what's my berth fee email say?"}))
    found, read = [m.content for m in model.seen[-1] if isinstance(m, ToolMessage)]
    assert "email: Harbour berth statement" in found and "from Sam Rivera" in found
    assert "120 EUR" in read and "Mooring invoice 7781" in read  # the mail and its attachment
    assert any(e["type"] == "results" and e["hits"][0]["kind"] == "mail" for e in events)


def test_removing_a_mailbox_forgets_everything_lumen_kept(env, local, filled):
    [hit] = [h for h in search(local, "berth") if h["kind"] == "mail"]
    local.post(f"/api/mail/messages/{hit['path'].removeprefix('mail:')}/attachments/0")
    assert (env.data / "mail-cache" / filled["id"]).exists()

    assert local.delete(f"/api/mail/accounts/{filled['id']}").json() == {"deleted": filled["email"]}
    assert search(local, "berth") == [] and search(local, "cedar") == []
    assert not (env.data / "mail-cache" / filled["id"]).exists()
    assert filled["id"] not in (env.data / "mail-secrets.json").read_text()
    assert local.get("/api/mail/accounts").json() == []
