"""Does a model work for the job it would do? Chat must call a tool when asked; images & video
must read the number on a test picture. Tried before a model is used."""

import logging

from . import backends, registry

log = logging.getLogger(__name__)


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


def ollama_caps(p: dict, model: str) -> list[str] | None:
    try:
        import ollama

        return list(ollama.Client(host=p["base_url"], timeout=15).show(model).capabilities or [])
    except Exception as e:
        if "not found" in str(e).lower():
            raise LookupError(f"{model} is not installed in Ollama. Download it first.") from e
        log.debug("capabilities of %s: %s", model, e)
        return None


def check(role: str, provider: str, model: str) -> dict:
    """Try a model on the job it would do. Returns {ok, checks: [{name, ok, detail}], seconds}.
    Chat must call a tool when asked; images & video must read text from a test picture."""
    import time

    p = registry.get(provider)
    model = (model or "").strip()
    started = time.time()
    checks: list[dict] = []

    def done(ok: bool) -> dict:
        return {"ok": ok, "checks": checks, "seconds": round(time.time() - started, 1)}

    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": ok, "detail": detail})
        return ok

    if role not in registry.ROLES:
        raise ValueError(f"Unknown role '{role}'")
    if p["kind"] == "ollama":
        try:
            caps = ollama_caps(p, model)
        except LookupError as e:
            add("Installed", False, str(e))
            return done(False)
        need = "tools" if role == "agent" else "vision"
        if caps is not None and need not in caps:
            add(
                "Supports " + ("tool calling" if role == "agent" else "images"),
                False,
                f"Ollama says {model} can't {'call tools' if role == 'agent' else 'see images'} "
                f"(it can: {', '.join(caps) or 'nothing listed'}).",
            )
            return done(False)

    if role == "agent":
        from langchain_core.tools import tool

        @tool
        def search_files(query: str) -> str:
            """Search the user's files by keywords."""
            return "no results"

        try:
            llm = backends.chat_model(provider, model, temperature=0, reasoning=False, num_ctx=4096)
            msg = llm.bind_tools([search_files]).invoke(
                "Find my files about invoices. Use the search_files tool; do not answer in text."
            )
        except Exception as e:
            log.info("check of %s (chat): %s", model, e)
            add("Answers", False, backends.why(e))
            return done(False)
        add("Answers", True, "The model replied.")
        calls = getattr(msg, "tool_calls", None) or []
        ok = any(c.get("name") == "search_files" for c in calls)
        add(
            "Calls tools",
            ok,
            f"Asked to search: called search_files({calls[0]['args'] if calls else ''})"
            if ok
            else "It answered in text instead of calling the search tool. "
            "The chat agent needs tool calling to find your files.",
        )
        return done(ok)

    try:
        reply = backends.describe_image(
            "What is the number written in this picture? Reply with just the number.",
            _test_image(),
            max_tokens=40,
            provider=provider,
            model=model,
        )
    except ConnectionError as e:
        add("Answers", False, str(e) or "Could not connect")
        return done(False)
    except Exception as e:
        log.info("check of %s (vision): %s", model, e)
        msg = backends.why(e)
        if any(w in msg.lower() for w in ("image", "vision", "multimodal")):
            msg = "It doesn't accept images: the server says this model has no image support."
        add("Accepts images", False, msg)
        return done(False)
    add("Accepts images", True, "The model took the picture.")
    ok = "4721" in reply.replace(" ", "")
    add("Reads the picture", ok, f'Test picture says 4721; it read "{reply[:80]}".')
    return done(ok)
