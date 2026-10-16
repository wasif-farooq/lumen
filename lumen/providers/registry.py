"""Which model providers exist and which model does each job.

A provider is the local Ollama server or any OpenAI-compatible API (LM Studio, llama.cpp,
vLLM, OpenAI, OpenRouter, ...). Jobs ("roles"): "agent" (chat + tools), "vision" (describes
images, scans and video frames while indexing) and "speech" (local whisper size).

Saved in providers.json in the data folder, readable only by the user: it can hold API keys,
so it is kept apart from settings.json, which the API hands out.
"""

import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from ..core import private_files
from ..core.settings import settings

ROLES = ("agent", "vision")
SPEECH_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
KINDS = ("ollama", "openai")


def _file() -> Path:
    return settings.data_dir / "providers.json"


def defaults() -> dict:
    return {"ollama": {"id": "ollama", "name": "Ollama", "kind": "ollama", "base_url": settings.ollama_host}}


settings.update(providers=defaults())


def load() -> None:
    """Apply saved providers and role choices (called with settings.load)."""
    try:
        saved = json.loads(_file().read_text())
    except (OSError, ValueError):
        return
    settings.update(
        providers={**defaults(), **{p["id"]: p for p in saved.get("providers", []) if p.get("kind") in KINDS}}
    )
    settings.update(ollama_host=settings.providers["ollama"]["base_url"])
    roles = saved.get("roles", {})
    for role, (prov_attr, model_attr) in _ROLE_ATTRS.items():
        r = roles.get(role) or {}
        if r.get("provider") in settings.providers and r.get("model"):
            settings.update(**{prov_attr: r["provider"], model_attr: r["model"]})
    if roles.get("speech", {}).get("model") in SPEECH_MODELS:
        settings.update(whisper_model=roles["speech"]["model"])


_ROLE_ATTRS = {"agent": ("agent_provider", "agent_model"), "vision": ("vision_provider", "caption_model")}


def _save() -> None:
    private_files.write_json(_file(), {"providers": list(settings.providers.values()), "roles": roles()})


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
        "id": p["id"],
        "name": p["name"],
        "kind": p["kind"],
        "base_url": p["base_url"],
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if len(key) >= 8 else "",
        "cloud": is_cloud(p),
        "builtin": p["id"] == "ollama",
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
    name = (data.get("name") or "").strip() or urlparse(url).hostname or "provider"
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


def remove(pid: str) -> None:
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
