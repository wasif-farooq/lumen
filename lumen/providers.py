"""Model providers and which model does each job.

A provider is the local Ollama server or any OpenAI-compatible API (LM Studio, llama.cpp,
vLLM, OpenAI, OpenRouter, ...). Roles: "agent" (chat + tools), "vision" (describes images,
scans and video frames while indexing) and "speech" (local whisper size).

Saved in providers.json in the data folder, readable only by the user: it can hold API keys,
so it is kept apart from settings.json, which the API hands out.
"""

import base64
import ipaddress
import json
import os
import re
import threading
from urllib.parse import urlparse
from .core import limits
from .core.settings import settings



ROLES = ("agent", "vision")
SPEECH_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
KINDS = ("ollama", "openai")


def _file():
    return settings.data_dir / "providers.json"


def _defaults() -> dict:
    return {"ollama": {"id": "ollama", "name": "Ollama", "kind": "ollama", "base_url": settings.ollama_host}}


settings.update(providers=_defaults())


def load():
    """Apply saved providers and role choices (called with settings.load)."""
    try:
        saved = json.loads(_file().read_text())
    except (OSError, ValueError):
        return
    settings.update(providers={**_defaults(), **{p["id"]: p for p in saved.get("providers", []) if p.get("kind") in KINDS}})
    settings.update(ollama_host=settings.providers["ollama"]["base_url"])
    roles = saved.get("roles", {})
    for role, (prov_attr, model_attr) in _ROLE_ATTRS.items():
        r = roles.get(role) or {}
        if r.get("provider") in settings.providers and r.get("model"):
            settings.update(**{prov_attr: r["provider"], model_attr: r["model"]})
    if roles.get("speech", {}).get("model") in SPEECH_MODELS:
        settings.update(whisper_model=roles["speech"]["model"])


_ROLE_ATTRS = {"agent": ("agent_provider", "agent_model"), "vision": ("vision_provider", "caption_model")}


def _save():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    f = _file()
    data = {"providers": list(settings.providers.values()), "roles": roles()}
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=1)
    os.chmod(f, 0o600)


def roles() -> dict:
    return {
        "agent": {"provider": settings.agent_provider, "model": settings.agent_model},
        "vision": {"provider": settings.vision_provider, "model": settings.caption_model},
        "speech": {"provider": "local", "model": settings.whisper_model},
    }


def get(pid: str) -> dict:
    if pid not in settings.providers:
        raise KeyError(f"No provider '{pid}'")
    return settings.providers[pid]


def is_cloud(p: dict) -> bool:
    """True when the provider is not on this laptop or the local network: file contents leave the machine."""
    host = urlparse(p.get("base_url", "")).hostname or ""
    if host in ("localhost", "host.docker.internal") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_loopback or ip.is_private or ip.is_link_local)
    except ValueError:
        return True  # a public host name


def public(p: dict) -> dict:
    """What the app may see: never the API key itself."""
    key = p.get("api_key") or ""
    return {
        "id": p["id"], "name": p["name"], "kind": p["kind"], "base_url": p["base_url"],
        "has_key": bool(key), "key_hint": f"…{key[-4:]}" if len(key) >= 8 else "",
        "cloud": is_cloud(p), "builtin": p["id"] == "ollama",
        "used_by": [r for r, v in roles().items() if v["provider"] == p["id"]],
    }


def upsert(data: dict) -> dict:
    """Add a provider, or update one (an empty api_key keeps the saved key)."""
    kind = data.get("kind", "openai")
    if kind not in KINDS:
        raise ValueError(f"Unknown provider type '{kind}'")
    url = (data.get("base_url") or "").strip().rstrip("/")
    if not re.match(r"^https?://[^/\s]+", url):
        raise ValueError("Address must start with http:// or https://")
    name = (data.get("name") or "").strip() or urlparse(url).hostname
    pid = data.get("id")
    if pid:
        p = dict(get(pid))
        if p["kind"] != kind:
            raise ValueError("A provider's type can't be changed; add a new one instead")
    else:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "provider"
        pid, n = base, 2
        while pid in settings.providers:
            pid, n = f"{base}-{n}", n + 1
        p = {"id": pid, "kind": kind}
    p.update(name=name, base_url=url)
    if data.get("api_key"):
        p["api_key"] = data["api_key"].strip()
    elif data.get("clear_key"):
        p.pop("api_key", None)
    settings.providers[pid] = p
    if pid == "ollama":
        settings.update(ollama_host=url)
    _save()
    return p


def remove(pid: str):
    p = get(pid)
    if pid == "ollama":
        raise ValueError("Ollama is built in; change its address instead")
    used = public(p)["used_by"]
    if used:
        raise ValueError(f"In use for {', '.join(used)}. Pick another model for it first.")
    del settings.providers[pid]
    _save()


def set_role(role: str, provider: str, model: str) -> dict:
    model = (model or "").strip()
    if role == "speech":
        if model not in SPEECH_MODELS:
            raise ValueError(f"Speech model must be one of {', '.join(SPEECH_MODELS)}")
        settings.update(whisper_model=model)
    elif role in _ROLE_ATTRS:
        get(provider)
        if not model:
            raise ValueError("Pick a model")
        prov_attr, model_attr = _ROLE_ATTRS[role]
        settings.update(**{prov_attr: provider, model_attr: model})
    else:
        raise ValueError(f"Unknown role '{role}'")
    _save()
    return roles()


def is_ollama(role: str) -> bool:
    return get(getattr(settings, _ROLE_ATTRS[role][0]))["kind"] == "ollama"


# ---------- talking to providers ----------

def _openai_client(p: dict):
    import openai

    return openai.OpenAI(base_url=p["base_url"], api_key=p.get("api_key") or "not-needed", timeout=120, max_retries=1)


def list_models(pid: str) -> list[dict]:
    """Models the provider offers: [{id, size, vision}] (vision None when the provider doesn't say)."""
    p = get(pid)
    if p["kind"] == "ollama":
        import ollama

        client = ollama.Client(host=p["base_url"], timeout=10)
        out = []
        for m in client.list().models:
            try:
                caps = client.show(m.model).capabilities or []
                vision, tools = "vision" in caps, "tools" in caps
            except Exception:
                vision = tools = None
            out.append({"id": m.model, "size": m.size, "vision": vision, "tools": tools})
        return sorted(out, key=lambda m: m["id"])
    try:
        models = _openai_client(p).models.list()
        return sorted(({"id": m.id, "size": None, "vision": None, "tools": None} for m in models), key=lambda m: m["id"])
    except Exception as e:
        raise ConnectionError(_why(e)) from e


def test(pid: str) -> dict:
    try:
        n = len(list_models(pid))
        return {"ok": True, "message": f"Connected · {n} model{'s' if n != 1 else ''} available"}
    except Exception as e:
        return {"ok": False, "message": _why(e)}


def _why(e: Exception) -> str:
    name = type(e).__name__
    if "Authentication" in name or "401" in str(e):
        return "The API key was rejected"
    if "Connect" in name or isinstance(e, ConnectionError):
        return "Could not connect. Check the address and that the server is running"
    return str(e)[:300] or name


def chat_model(provider: str | None = None, model: str | None = None, **ollama_options):
    """LangChain chat model for the agent role (or the given provider/model).
    ollama_options only apply to Ollama."""
    p = get(provider or settings.agent_provider)
    model = model or settings.agent_model
    if p["kind"] == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=p["base_url"], **ollama_options)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model, base_url=p["base_url"], api_key=p.get("api_key") or "not-needed",
        temperature=ollama_options.get("temperature", 0), timeout=120, max_retries=1,
    )


def describe_image(prompt: str, png: bytes, max_tokens: int = 200, provider: str | None = None, model: str | None = None) -> str:
    """One image + prompt to the vision role's model (or the given provider/model); returns the reply
    on one line. Raises ConnectionError when the provider can't be reached (indexing then stops that pass)."""
    p = get(provider or settings.vision_provider)
    model = model or settings.caption_model
    if p["kind"] == "ollama":
        import ollama

        resp = ollama.Client(host=p["base_url"]).chat(
            model=model,
            messages=[{"role": "user", "content": prompt, "images": [png]}],
            think=False,
            keep_alive=limits.INDEX_KEEP_ALIVE,
            options=settings.ollama_options(num_predict=max_tokens, num_ctx=4096, temperature=0),
        )
        return " ".join(resp.message.content.split())
    import openai

    url = "data:image/png;base64," + base64.b64encode(png).decode()
    try:
        resp = _openai_client(p).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
            max_tokens=max_tokens,
            temperature=0,
        )
    except (openai.APIConnectionError, openai.AuthenticationError) as e:
        raise ConnectionError(_why(e)) from e
    return " ".join((resp.choices[0].message.content or "").split())


# ---------- does a model work for a job? ----------

def _test_image() -> bytes:
    """A small picture with a word and a number on it, for the vision check."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGB", (480, 200), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.load_default(size=56)
    except TypeError:  # older Pillow
        font = ImageFont.load_default()
    d.rectangle((20, 20, 460, 180), outline="black", width=4)
    d.text((60, 60), "CODE 4721", fill="black", font=font)
    buf = BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _ollama_caps(p: dict, model: str) -> list[str] | None:
    try:
        import ollama

        return list(ollama.Client(host=p["base_url"], timeout=15).show(model).capabilities or [])
    except Exception as e:
        if "not found" in str(e).lower():
            raise LookupError(f"{model} is not installed in Ollama. Download it first.") from e
        return None


def check(role: str, provider: str, model: str) -> dict:
    """Try a model on the job it would do. Returns {ok, checks: [{name, ok, detail}], seconds}.
    Chat must call a tool when asked; images & video must read text from a test picture."""
    import time

    p = get(provider)
    model = (model or "").strip()
    started = time.time()
    checks: list[dict] = []

    def done(ok: bool) -> dict:
        return {"ok": ok, "checks": checks, "seconds": round(time.time() - started, 1)}

    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": ok, "detail": detail})
        return ok

    if role not in ROLES:
        raise ValueError(f"Unknown role '{role}'")
    if p["kind"] == "ollama":
        try:
            caps = _ollama_caps(p, model)
        except LookupError as e:
            add("Installed", False, str(e))
            return done(False)
        need = "tools" if role == "agent" else "vision"
        if caps is not None and need not in caps:
            add("Supports " + ("tool calling" if role == "agent" else "images"), False,
                f"Ollama says {model} can't {'call tools' if role == 'agent' else 'see images'} "
                f"(it can: {', '.join(caps) or 'nothing listed'}).")
            return done(False)

    if role == "agent":
        from langchain_core.tools import tool

        @tool
        def search_files(query: str) -> str:
            """Search the user's files by keywords."""
            return "no results"

        try:
            llm = chat_model(provider, model, temperature=0, reasoning=False, num_ctx=4096)
            msg = llm.bind_tools([search_files]).invoke(
                "Find my files about invoices. Use the search_files tool; do not answer in text.")
        except Exception as e:
            add("Answers", False, _why(e))
            return done(False)
        add("Answers", True, "The model replied.")
        calls = getattr(msg, "tool_calls", None) or []
        ok = any(c.get("name") == "search_files" for c in calls)
        add("Calls tools", ok, f"Asked to search: called search_files({calls[0]['args'] if calls else ''})" if ok else
            "It answered in text instead of calling the search tool. The chat agent needs tool calling to find your files.")
        return done(ok)

    try:
        reply = describe_image("What is the number written in this picture? Reply with just the number.",
                               _test_image(), max_tokens=40, provider=provider, model=model)
    except ConnectionError as e:
        add("Answers", False, str(e) or "Could not connect")
        return done(False)
    except Exception as e:
        msg = _why(e)
        if any(w in msg.lower() for w in ("image", "vision", "multimodal")):
            msg = "It doesn't accept images: the server says this model has no image support."
        add("Accepts images", False, msg)
        return done(False)
    add("Accepts images", True, "The model took the picture.")
    ok = "4721" in reply.replace(" ", "")
    add("Reads the picture", ok, f'Test picture says 4721; it read "{reply[:80]}".')
    return done(ok)


# ---------- pulling Ollama models ----------

_pulls: dict[str, dict] = {}  # model -> {status, completed, total, done, error}


def pull(model: str) -> dict:
    """Start downloading an Ollama model in the background; poll pull_status()."""
    model = model.strip()
    if not model:
        raise ValueError("Enter a model name, e.g. qwen2.5vl:3b")
    cur = _pulls.get(model)
    if cur and not cur["done"]:
        return cur
    st = _pulls[model] = {"model": model, "status": "starting", "completed": 0, "total": 0, "done": False, "error": None}

    def run():
        import ollama

        try:
            for ev in ollama.Client(host=settings.providers["ollama"]["base_url"]).pull(model, stream=True):
                st.update(status=ev.status or st["status"], completed=ev.completed or st["completed"], total=ev.total or st["total"])
            st["status"] = "done"
        except Exception as e:
            st["error"] = _why(e) if not isinstance(e, ollama.ResponseError) else str(e.error)
        finally:
            st["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return st


def pull_status() -> list[dict]:
    return list(_pulls.values())
