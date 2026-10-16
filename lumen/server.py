"""HTTP API for the desktop and mobile app.

    lumen serve          # this laptop only (127.0.0.1:8765)
    lumen serve --lan    # also paired phones on the local network

Requests from this machine need no token. Phones pair with a 6-digit code shown
in the desktop app and then send `Authorization: Bearer <token>`.
"""

import hashlib
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import config, index, power, providers, settings
from .media import MEDIA_EXTS, fmt_time
from .tools import RUNNABLE_EXTS, _allowed, _launch

app = FastAPI(title="Lumen")
_model_lock = threading.Lock()  # one local model: answer one chat at a time
_sessions: dict = {}
_state = {"lan": False}


# ---------- auth ----------

def _is_local(request: Request) -> bool:
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost")


def _devices_file() -> Path:
    return config.DATA_DIR / "devices.json"


def _devices() -> list[dict]:
    try:
        return json.loads(_devices_file().read_text())
    except (OSError, ValueError):
        return []


def _save_devices(devices: list[dict]):
    f = _devices_file()
    f.write_text(json.dumps(devices, indent=1))
    f.chmod(0o600)


def auth(request: Request):
    if _is_local(request):
        return "local"
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    for d in _devices():
        if token and secrets.compare_digest(d["token_sha256"], digest):
            return d["id"]
    raise HTTPException(401, "Not paired")


def local_only(request: Request):
    if not _is_local(request):
        raise HTTPException(403, "Only from the laptop itself")


# ---------- chats (history for the UI; the model's memory is in the checkpointer) ----------

def _db() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATA_DIR / "chats.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT, created REAL, updated REAL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, chat_id TEXT, at REAL, type TEXT, data TEXT);
        CREATE INDEX IF NOT EXISTS events_chat ON events(chat_id);
    """)
    return conn


_chat_db = None
_saver = None


def chat_db():
    global _chat_db
    if _chat_db is None:
        _chat_db = _db()
    return _chat_db


def saver():
    global _saver
    if _saver is None:
        from langgraph.checkpoint.sqlite import SqliteSaver

        _saver = SqliteSaver(sqlite3.connect(config.DATA_DIR / "memory.db", check_same_thread=False))
    return _saver


def session_for(chat_id: str):
    from .agent import Session

    if chat_id not in _sessions:
        _sessions[chat_id] = Session(thread_id=chat_id, checkpointer=saver(), app=True)
    return _sessions[chat_id]


def _log(chat_id: str, kind: str, data: dict):
    db = chat_db()
    db.execute("INSERT INTO events (chat_id, at, type, data) VALUES (?,?,?,?)", (chat_id, time.time(), kind, json.dumps(data)))
    db.execute("UPDATE chats SET updated=? WHERE id=?", (time.time(), chat_id))
    db.commit()


class NewChat(BaseModel):
    title: str | None = None


class Ask(BaseModel):
    text: str


@app.get("/api/chats")
def list_chats(_=Depends(auth)):
    rows = chat_db().execute("SELECT * FROM chats ORDER BY updated DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/chats")
def create_chat(body: NewChat, _=Depends(auth)):
    chat = {"id": str(uuid.uuid4()), "title": body.title or "New chat", "created": time.time(), "updated": time.time()}
    chat_db().execute("INSERT INTO chats VALUES (:id, :title, :created, :updated)", chat)
    chat_db().commit()
    return chat


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, _=Depends(auth)):
    chat_db().execute("DELETE FROM events WHERE chat_id=?", (chat_id,))
    chat_db().execute("DELETE FROM chats WHERE id=?", (chat_id,))
    chat_db().commit()
    _sessions.pop(chat_id, None)
    return {"ok": True}


@app.get("/api/chats/{chat_id}/events")
def chat_events(chat_id: str, _=Depends(auth)):
    rows = chat_db().execute("SELECT type, data, at FROM events WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
    return [{"type": r["type"], "at": r["at"], **json.loads(r["data"])} for r in rows]


@app.post("/api/chats/{chat_id}/messages")
def send_message(chat_id: str, body: Ask, _=Depends(auth)):
    """Stream the agent's work as server-sent events (one JSON object per `data:` line)."""
    row = chat_db().execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No such chat")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty message")
    if row["title"] == "New chat":
        title = text if len(text) <= 48 else text[:45].rsplit(" ", 1)[0] + "…"
        chat_db().execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))
        chat_db().commit()
    _log(chat_id, "user", {"text": text})

    return _stream(chat_id, lambda s: s.stream(text))


def _stream(chat_id: str, run):
    """Stream the agent's events as server-sent events and record them in the chat history."""

    def events():
        def send(kind, data):
            _log(chat_id, kind, data)
            return f"data: {json.dumps({'type': kind, **data})}\n\n"

        reindex = False
        yield f"data: {json.dumps({'type': 'started'})}\n\n"
        with _model_lock:
            try:
                for kind, payload in run(session_for(chat_id)):
                    if kind == "tool_call":
                        yield send("tool_call", {"name": payload[0], "args": payload[1]})
                    elif kind == "ui":
                        if payload["type"] == "action_done" and not payload.get("dry_run") and payload.get("op") != "move":
                            reindex = True  # new files from a copy/create: index them
                        yield send(payload["type"], {k: v for k, v in payload.items() if k != "type"})
                    elif kind == "approval":
                        yield send("approval", {k: v for k, v in payload.items() if k != "type"})
                    elif kind == "answer":
                        yield send("answer", {"text": payload or ""})
            except Exception as e:  # loop limit, Ollama down, …: tell the UI instead of dropping the stream
                yield send("error", {"text": _friendly(e)})
        if reindex:
            _indexer.start()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class Decision(BaseModel):
    approved: bool


@app.post("/api/chats/{chat_id}/approve")
def approve(chat_id: str, body: Decision, _=Depends(auth)):
    """Answer the agent's pending change request (Approve / Cancel) and stream what happens next."""
    if session_for(chat_id).waiting is None:
        raise HTTPException(409, "Nothing is waiting for approval in this chat")
    _log(chat_id, "approval_answer", {"approved": body.approved})
    return _stream(chat_id, lambda s: s.resume(body.approved))


@app.get("/api/chats/{chat_id}/pending")
def pending(chat_id: str, _=Depends(auth)):
    return {"pending": session_for(chat_id).waiting}


class UndoReq(BaseModel):
    chat_id: str | None = None


@app.post("/api/actions/{action_id}/undo")
def undo_action(action_id: str, body: UndoReq, _=Depends(auth)):
    from . import fileops

    try:
        msg = fileops.undo(action_id)
    except (fileops.FileOpError, OSError) as e:
        raise HTTPException(400, str(e))
    if body.chat_id:
        _log(body.chat_id, "undone", {"action_id": action_id, "text": msg})
    return {"ok": True, "message": msg}


@app.get("/api/actions")
def actions(_=Depends(auth)):
    from . import fileops

    return list(reversed(fileops.history()))[:100]


def _friendly(e: Exception) -> str:
    name = type(e).__name__
    if name == "GraphRecursionError":
        return "I went in circles on that one and stopped. Try rephrasing it more specifically."
    if isinstance(e, ConnectionError) or "connect" in str(e).lower():
        return f"Can't reach the local model (Ollama at {config.OLLAMA_HOST}). Is it running?"
    return f"Something went wrong: {e}"


# ---------- images: visual search, similar ----------

def _similar_and_log(chat_id: str, source, label: dict) -> list[dict]:
    """Run a similar-image search for an app button/upload and record it in the chat."""
    from . import visual
    from .tools import image_hits

    if not chat_db().execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone():
        raise HTTPException(404, "No such chat")
    conn = index.connect()
    try:
        hits = image_hits(conn, visual.similar_to(conn, source))
    finally:
        conn.close()
    title = chat_db().execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()["title"]
    if title == "New chat":
        chat_db().execute("UPDATE chats SET title=? WHERE id=?", (label["text"][:48], chat_id))
        chat_db().commit()
    _log(chat_id, "user", label)
    _log(chat_id, "results", {"hits": hits})
    # so "open the second one" in the next message refers to these
    session_for(chat_id).state.setdefault("last_results", [])[:] = [h["path"] for h in hits]
    return hits


@app.get("/api/images/search")
def image_search(q: str, folder: str = "", limit: int = 12, _=Depends(auth)):
    from .tools import hybrid_image_search

    conn = index.connect()
    try:
        return hybrid_image_search(conn, q, limit=min(max(limit, 1), 50), folder=folder)
    finally:
        conn.close()


@app.get("/api/images/similar")
def image_similar(path: str, _=Depends(auth)):
    from . import visual
    from .tools import image_hits

    p = _checked(path)
    conn = index.connect()
    try:
        return image_hits(conn, visual.similar_to(conn, str(p)))
    finally:
        conn.close()


class SimilarReq(BaseModel):
    path: str


@app.post("/api/chats/{chat_id}/similar")
def chat_similar(chat_id: str, body: SimilarReq, _=Depends(auth)):
    p = _checked(body.path)
    return _similar_and_log(chat_id, str(p), {"text": f"Images like {p.name}", "image_path": str(p)})


@app.post("/api/chats/{chat_id}/similar-upload")
async def chat_similar_upload(chat_id: str, request: Request, _=Depends(auth)):
    """Raw image bytes in the body (a dropped file or a phone photo); the photo is kept, downscaled,
    so the chat can show it."""
    from io import BytesIO

    from . import visual

    data = await request.body()
    if not data or len(data) > 30 * 1024 * 1024:
        raise HTTPException(400, "Send one image up to 30 MB")
    try:
        im = visual.open_image(data)
    except Exception:
        raise HTTPException(400, "That file is not an image I can read")
    im = im.convert("RGB")
    im.thumbnail((1024, 1024))
    upload_id = hashlib.sha1(data).hexdigest()[:20]
    folder = config.DATA_DIR / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=88)
    (folder / f"{upload_id}.jpg").write_bytes(buf.getvalue())
    return _similar_and_log(chat_id, buf.getvalue(), {"text": "Images like this photo", "upload": upload_id})


@app.get("/api/uploads/{upload_id}")
def get_upload(upload_id: str, _=Depends(auth)):
    if not upload_id.isalnum():
        raise HTTPException(400, "Bad id")
    f = config.DATA_DIR / "uploads" / f"{upload_id}.jpg"
    if not f.exists():
        raise HTTPException(404, "Not found")
    return Response(f.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


# ---------- files ----------

@app.get("/api/search")
def search(q: str = "", ext: str = "", after: str = "", before: str = "", folder: str = "", limit: int = 20,
           min_minutes: float = 0, max_minutes: float = 0, _=Depends(auth)):
    hits = index.search(q, ext, after, before, folder, min(max(limit, 1), 100), min_minutes, max_minutes)
    return [h.to_dict() for h in hits]


@app.get("/api/file")
def file_info(path: str, at: float | None = None, _=Depends(auth)):
    p = _checked(path)
    st = p.stat()
    ext = p.suffix.lower().lstrip(".")
    conn = index.connect()
    try:
        row = conn.execute("SELECT id, caption, duration, has_text FROM files WHERE path=?", (str(p),)).fetchone()
        segments = []
        if row and ext in MEDIA_EXTS:
            if at is not None:
                q = "SELECT start, end, text FROM segments WHERE file_id=? AND start BETWEEN ? AND ? ORDER BY start"
                segs = conn.execute(q, (row["id"], at - 30, at + 60)).fetchall()
            else:
                segs = conn.execute("SELECT start, end, text FROM segments WHERE file_id=? ORDER BY start LIMIT 300", (row["id"],)).fetchall()
            segments = [{"start": s["start"], "end": s["end"], "text": s["text"], "time": fmt_time(s["start"])} for s in segs]
    finally:
        conn.close()
    text = index.indexed_text(str(p))
    return {
        "path": str(p), "name": p.name, "ext": ext, "kind": index.kind_of(ext), "size": st.st_size, "mtime": st.st_mtime,
        "folder": str(p.parent), "indexed": row is not None, "searchable": bool(row and (row["has_text"] or row["caption"])),
        "caption": (row["caption"] if row else "") or "", "duration": row["duration"] if row else None,
        "excerpt": text[:1500], "segments": segments,
    }


@app.get("/api/thumb")
def thumb(path: str, w: int = 480, t: float | None = None, _=Depends(auth)):
    p = _checked(path)
    w = max(64, min(w, 1600))
    st = p.stat()
    key = hashlib.sha1(f"{p}|{st.st_mtime}|{w}|{t}".encode()).hexdigest()
    cache = config.DATA_DIR / "thumbs" / f"{key}.png"
    if not cache.exists():
        png = _render_thumb(p, w, t)
        if png is None:
            raise HTTPException(404, "No preview for this file type")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(png)
    return Response(cache.read_bytes(), media_type="image/png", headers={"Cache-Control": "max-age=86400"})


def _render_thumb(p: Path, w: int, t: float | None) -> bytes | None:
    from io import BytesIO

    ext = p.suffix.lower().lstrip(".")
    kind = index.kind_of(ext)
    try:
        if kind == "video":
            from .media import probe

            at = t if t is not None else max(1.0, probe(str(p))["duration"] * 0.15)
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-threads", "1", "-ss", f"{at:.2f}", "-i", str(p), "-frames:v", "1",
                 "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                capture_output=True, timeout=60,
            ).stdout
            return out or None
        if kind in ("pdf", "image"):
            import pymupdf

            try:
                with pymupdf.open(p) as doc:
                    page = doc[0]
                    zoom = w / page.rect.width
                    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
            except Exception:
                if kind == "pdf":
                    return None
            from PIL import Image

            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((w, w * 2))
                buf = BytesIO()
                im.save(buf, "PNG")
                return buf.getvalue()
    except Exception:
        return None
    return None


class OpenReq(BaseModel):
    path: str
    start_seconds: float = 0


@app.post("/api/open")
def open_file(body: OpenReq, _=Depends(auth)):
    p = _checked(body.path)
    ext = p.suffix.lower().lstrip(".")
    if p.is_file() and (ext in RUNNABLE_EXTS or os.access(p, os.X_OK)):
        return {"ok": True, "message": "Scripts and programs open their folder instead. " + _launch(p.parent)}
    return {"ok": True, "message": _launch(p, body.start_seconds if ext in MEDIA_EXTS else 0)}


@app.post("/api/show")
def show_in_folder(body: OpenReq, _=Depends(auth)):
    p = _checked(body.path)
    return {"ok": True, "message": _launch(p if p.is_dir() else p.parent)}


def _checked(path: str) -> Path:
    try:
        p = _allowed(path)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    if not p.exists():
        raise HTTPException(404, "File not found")
    return p


# ---------- status, settings, indexing ----------

@app.get("/api/status")
def status(_=Depends(auth)):
    try:
        last = json.loads((config.DATA_DIR / "last_index.json").read_text())
    except (OSError, ValueError):
        last = None
    try:
        import ollama

        loaded = [m.model for m in ollama.Client(host=config.OLLAMA_HOST).ps().models]
        ollama_ok = True
    except Exception:
        loaded, ollama_ok = [], False
    allowed, why = power.heavy_allowed()
    return {
        "host": socket.gethostname(),
        "index": index.stats(),
        "last_index": last,
        "indexing": _indexer.running,
        "index_paused": _indexer.state["paused"],
        "folders": [{"path": str(r), "files": _count_under(r), "paused": r in config.PAUSED_ROOTS} for r in config.ROOTS],
        "power": {"on_ac": power.on_ac(), "battery": power.battery_percent(), "mode": config.POWER_MODE,
                  "ai_allowed": allowed, "reason": why, "threads": power.threads()},
        "models": {"agent": config.AGENT_MODEL, "vision": config.CAPTION_MODEL, "speech": f"whisper-{config.WHISPER_MODEL}",
                   "agent_provider": providers.get(config.AGENT_PROVIDER)["name"],
                   "vision_provider": providers.get(config.VISION_PROVIDER)["name"],
                   "agent_cloud": providers.is_cloud(providers.get(config.AGENT_PROVIDER)),
                   "vision_cloud": providers.is_cloud(providers.get(config.VISION_PROVIDER)),
                   "cpu_only": config.CPU_ONLY, "ollama_ok": ollama_ok, "loaded": loaded},
        "langfuse": bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
        "langfuse_host": os.environ.get("LANGFUSE_HOST", ""),
        "lan": _state["lan"],
        "open_mode": config.OPEN_MODE,
    }


def _count_under(root: Path) -> int:
    conn = index.connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM files WHERE path LIKE ?", (str(root) + os.sep + "%",)).fetchone()[0]
    finally:
        conn.close()


@app.get("/api/settings")
def get_settings(_=Depends(auth)):
    return settings.current()


@app.put("/api/settings")
def put_settings(body: dict, _=Depends(local_only)):
    before = config.CPU_ONLY
    if "roots" in body:
        try:
            settings.check_roots(body["roots"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    roots_before = list(config.ROOTS)
    out = settings.update(body)
    if config.CPU_ONLY != before or config.ROOTS != roots_before:
        _sessions.clear()  # rebuild agents with the new GPU/CPU choice / folder list
    return out


class Indexer:
    def __init__(self):
        self.proc = None
        self.lines = deque(maxlen=300)
        self.started = None
        self.pause_file = config.DATA_DIR / "index.pause"
        self.pause_file.unlink(missing_ok=True)  # a flag left by a crash would hold the next run
        self._reset()

    def _reset(self):
        self.state = {"phase": None, "done": 0, "total": 0, "path": None, "note": None, "scanned": 0,
                      "ext": None, "kind": None, "paused": False, "summary": None}
        self.recent = deque(maxlen=8)  # last files finished: {phase, path, note}
        self.phase_started = time.time()
        self.paused_since = None
        self.paused_in_phase = 0.0  # seconds, so the time-left estimate ignores pauses

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def pause_requested(self) -> bool:
        return self.pause_file.exists()

    def start(self):
        if self.running:
            return
        self.pause_file.unlink(missing_ok=True)
        self.lines.clear()
        self._reset()
        self.started = time.time()
        # Separate process: its low priority (nice/ionice) never slows the API or chat
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lumen", "index"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "COLUMNS": "200", "LUMEN_DATA": str(config.DATA_DIR), "PYTHONUNBUFFERED": "1",
                 "LUMEN_EVENTS": "1", "LUMEN_PAUSE_FILE": str(self.pause_file)},
            start_new_session=True,  # own process group, so Stop also ends its ffmpeg children
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def pause(self) -> bool:
        """Ask indexing to hold after the file it is on. It saves its work first, so the
        database is never locked while paused."""
        if not self.running:
            return False
        self.pause_file.touch()
        return True

    def resume(self) -> bool:
        self.pause_file.unlink(missing_ok=True)
        return self.running

    def stop(self) -> bool:
        """Stop indexing. Work already saved stays; the next run continues with what is left."""
        self.pause_file.unlink(missing_ok=True)
        if not self.running:
            return False
        import signal

        pgid = os.getpgid(self.proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            self.proc.wait(timeout=5)
        self.lines.append("Stopped. Finished work is saved; the next run continues with the rest.")
        return True

    def _event(self, e: dict):
        st, now = self.state, time.time()
        if "phase" in e:
            st.update(phase=e["phase"], done=0, total=0, path=None, note=None)
            self.phase_started, self.paused_in_phase = now, 0.0
        if "scanned" in e:
            st["scanned"] = e["scanned"]
        if "item" in e:
            it = e["item"]
            ext = Path(it["path"]).suffix.lower().lstrip(".")
            st.update(done=it["done"], total=it["total"], path=it["path"], note=it["note"], ext=ext, kind=index.kind_of(ext))
            entry = {"phase": st["phase"], "path": it["path"], "note": it["note"], "ext": ext, "kind": st["kind"]}
            if self.recent and self.recent[0]["path"] == it["path"]:
                self.recent[0] = entry  # video/audio report several steps for one file
            else:
                self.recent.appendleft(entry)
        if "paused" in e:
            st["paused"] = bool(e["paused"])
            if st["paused"]:
                self.paused_since = now
            elif self.paused_since:
                self.paused_in_phase += now - self.paused_since
                self.paused_since = None
        if "summary" in e:
            st["summary"] = e["summary"]

    def _pump(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            if line.startswith("@@"):
                try:
                    self._event(json.loads(line[2:]))
                except (ValueError, KeyError, TypeError):
                    pass
            elif line and "onnxruntime" not in line and "HF Hub" not in line:
                self.lines.append(line)
        self.pause_file.unlink(missing_ok=True)
        self.state["paused"] = False

    def progress(self) -> dict:
        st = self.state
        eta = None
        if self.running and st["total"] and 0 < st["done"] < st["total"]:
            paused = self.paused_in_phase + (time.time() - self.paused_since if self.paused_since else 0)
            active = time.time() - self.phase_started - paused
            eta = round(active / st["done"] * (st["total"] - st["done"]))
        return {"running": self.running, "started": self.started, **st,
                "pausing": self.running and self.pause_requested and not st["paused"],
                "eta": eta, "recent": list(self.recent), "lines": list(self.lines)}


_indexer = Indexer()


@app.on_event("shutdown")
def _stop_indexing_on_exit():
    # The indexer runs in its own process group: end it with the server, so nothing keeps
    # running from an app bundle (e.g. an AppImage) after the app is closed.
    _indexer.stop()


@app.post("/api/index")
def run_index(_=Depends(auth)):
    _indexer.start()
    return {"running": True}


@app.post("/api/index/stop")
def stop_index(_=Depends(auth)):
    return {"stopped": _indexer.stop(), "running": _indexer.running}


@app.post("/api/index/pause")
def pause_index(_=Depends(auth)):
    return {"pausing": _indexer.pause(), "running": _indexer.running}


@app.post("/api/index/resume")
def resume_index(_=Depends(auth)):
    return {"running": _indexer.resume()}


@app.get("/api/index")
def index_progress(_=Depends(auth)):
    return _indexer.progress()


class PathBody(BaseModel):
    path: str
    reindex: bool = False


def _not_while_indexing():
    # A running index already read the folder list and exclusions, so it would undo the change
    if _indexer.running:
        raise HTTPException(409, "Indexing is running. Wait for it to finish, or stop it, then try again.")


def _root(path: str) -> Path:
    r = Path(path).expanduser().resolve()
    if r not in config.ROOTS:
        raise HTTPException(404, f"Not an indexed folder: {r}")
    return r


@app.post("/api/index/exclude")
def exclude_path(body: PathBody, _=Depends(local_only)):
    """Drop a file or folder from the index and keep it out of later runs."""
    _not_while_indexing()
    p = Path(body.path).expanduser().resolve()
    if not any(p.is_relative_to(r) for r in config.ROOTS):
        raise HTTPException(400, f"Not inside an indexed folder: {p}")
    if p in config.ROOTS:
        raise HTTPException(400, "To drop a whole folder, remove it from the folder list instead")
    removed = index.forget(str(p))
    settings.update({"excluded": [*config.EXCLUDED, str(p)]})
    return {"removed": removed, "excluded": config.EXCLUDED}


@app.post("/api/index/include")
def include_path(body: PathBody, _=Depends(local_only)):
    """Let an excluded file or folder back in; it is indexed on the next run (now, by default)."""
    _not_while_indexing()
    p = str(Path(body.path).expanduser().resolve())
    settings.update({"excluded": [e for e in config.EXCLUDED if e != p]})
    if body.reindex:
        _indexer.start()
    return {"excluded": config.EXCLUDED}


@app.post("/api/folders/pause")
def pause_folder(body: PathBody, _=Depends(local_only)):
    """Keep a folder's files searchable but stop re-scanning it."""
    _not_while_indexing()
    r = _root(body.path)
    settings.update({"paused_roots": [*(p for p in config.PAUSED_ROOTS if p != r), r]})
    return {"paused": True}


@app.post("/api/folders/resume")
def resume_folder(body: PathBody, _=Depends(local_only)):
    _not_while_indexing()
    r = _root(body.path)
    settings.update({"paused_roots": [p for p in config.PAUSED_ROOTS if p != r]})
    if body.reindex:
        _indexer.start()  # catch up on what changed while it was paused
    return {"paused": False}


@app.post("/api/folders/clear")
def clear_folder(body: PathBody, _=Depends(local_only)):
    """Drop everything indexed under a folder. The files themselves are not touched."""
    _not_while_indexing()
    r = _root(body.path)
    removed = index.forget(str(r))
    if body.reindex and r not in config.PAUSED_ROOTS:
        _indexer.start()
    return {"removed": removed}


# ---------- model providers ----------

def _provider_call(fn, *a):
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, e.args[0] if e.args else "Not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/providers")
def list_providers(_=Depends(auth)):
    return {"providers": [providers.public(p) for p in config.PROVIDERS.values()], "roles": providers.roles(),
            "speech_models": providers.SPEECH_MODELS, "pulls": providers.pull_status()}


@app.post("/api/providers")
def save_provider(body: dict, _=Depends(local_only)):
    p = _provider_call(providers.upsert, body)
    _sessions.clear()  # chats pick up a changed address or key
    return providers.public(p)


@app.delete("/api/providers/{pid}")
def delete_provider(pid: str, _=Depends(local_only)):
    _provider_call(providers.remove, pid)
    return {"deleted": pid}


@app.get("/api/providers/{pid}/models")
def provider_models(pid: str, _=Depends(local_only)):
    try:
        return _provider_call(providers.list_models, pid)
    except ConnectionError as e:
        raise HTTPException(502, str(e) or "Could not connect")
    except Exception as e:
        raise HTTPException(502, providers._why(e))


@app.post("/api/providers/{pid}/test")
def test_provider(pid: str, _=Depends(local_only)):
    return _provider_call(providers.test, pid)


class PullReq(BaseModel):
    model: str


@app.post("/api/providers/ollama/pull")
def pull_model(body: PullReq, _=Depends(local_only)):
    return _provider_call(providers.pull, body.model)


class RoleReq(BaseModel):
    role: str
    provider: str = "local"
    model: str


class CheckReq(BaseModel):
    role: str
    provider: str
    model: str


@app.post("/api/models/check")
def check_model(body: CheckReq, _=Depends(local_only)):
    """Try a model on a job before using it (can take a minute while a local model loads)."""
    return _provider_call(providers.check, body.role, body.provider, body.model)


@app.put("/api/roles")
def set_role(body: RoleReq, _=Depends(local_only)):
    out = _provider_call(providers.set_role, body.role, body.provider, body.model)
    if body.role == "agent":
        _sessions.clear()  # new chats use the new model
    return out


# ---------- phone pairing ----------

_pair = {"code": None, "expires": 0.0, "tries": 0}


@app.post("/api/pair/start")
def pair_start(_=Depends(local_only)):
    _pair.update(code=f"{secrets.randbelow(10**6):06d}", expires=time.time() + 120, tries=0)
    return {"code": _pair["code"], "expires_in": 120, "lan": _state["lan"], "address": f"{_lan_ip()}:{_state.get('port', 8765)}"}


class PairReq(BaseModel):
    code: str
    name: str = "Phone"


@app.post("/api/pair")
def pair(body: PairReq):
    ok = (
        _pair["code"] is not None and time.time() < _pair["expires"] and _pair["tries"] < 5
        and secrets.compare_digest(body.code.strip(), _pair["code"])
    )
    _pair["tries"] += 1
    if not ok:
        raise HTTPException(403, "Wrong or expired code")
    _pair["code"] = None
    token = secrets.token_urlsafe(32)
    device = {"id": str(uuid.uuid4()), "name": body.name[:60], "paired": time.time(),
              "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    _save_devices([*_devices(), device])
    return {"token": token, "host": socket.gethostname(), "device_id": device["id"]}


@app.get("/api/devices")
def devices(_=Depends(local_only)):
    return [{k: d[k] for k in ("id", "name", "paired")} for d in _devices()]


@app.delete("/api/devices/{device_id}")
def unpair(device_id: str, _=Depends(local_only)):
    _save_devices([d for d in _devices() if d["id"] != device_id])
    return {"ok": True}


@app.get("/api/hello")
def hello():
    """Unauthenticated: lets a phone check it found an Lumen before pairing."""
    return {"app": "lumen", "host": socket.gethostname()}


# ---------- run ----------

def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _advertise(port: int):
    """Announce the server on the LAN (mDNS) so the phone app can find it."""
    from zeroconf import ServiceInfo, Zeroconf

    host = socket.gethostname()
    info = ServiceInfo(
        "_lumen._tcp.local.", f"{host}._lumen._tcp.local.",
        addresses=[socket.inet_aton(_lan_ip())], port=port, properties={"host": host}, server=f"{host}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    return zc


def run(lan: bool = False, port: int = 8765):
    import uvicorn

    _state.update(lan=lan, port=port)
    zc = _advertise(port) if lan else None
    where = f"0.0.0.0:{port} (LAN {_lan_ip()}:{port})" if lan else f"127.0.0.1:{port}"
    print(f"lumen API on {where} · model {config.AGENT_MODEL}", flush=True)
    try:
        uvicorn.run(app, host="0.0.0.0" if lan else "127.0.0.1", port=port, log_level="warning")
    finally:
        if zc:
            zc.close()
