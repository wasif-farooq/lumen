"""Talking to model providers (Adapter): the local Ollama server and OpenAI-compatible APIs
look the same to the rest of Lumen: a chat model, describe an image, list models."""

import base64
import logging

from ..core import limits
from ..core.settings import settings
from . import registry

log = logging.getLogger(__name__)


def why(e: Exception) -> str:
    """A provider error in words people understand."""
    name = type(e).__name__
    if "Authentication" in name or "401" in str(e):
        return "The API key was rejected"
    if "Connect" in name or isinstance(e, ConnectionError):
        return "Could not connect. Check the address and that the server is running"
    return str(e)[:300] or name


class Backend:
    """One provider (its saved entry: id, name, kind, base_url, maybe api_key)."""

    def __init__(self, provider: dict):
        self.p = provider

    def chat_model(self, model: str, **ollama_options):
        """A LangChain chat model; ollama_options only apply to Ollama."""
        raise NotImplementedError

    def describe_image(self, model: str, prompt: str, png: bytes, max_tokens: int) -> str:
        raise NotImplementedError

    def list_models(self) -> list[dict]:
        """[{id, size, vision, tools}]; vision/tools are None when the provider doesn't say."""
        raise NotImplementedError


class OllamaBackend(Backend):
    def _client(self, timeout=None):
        import ollama

        return ollama.Client(host=self.p["base_url"], **({"timeout": timeout} if timeout else {}))

    def chat_model(self, model, **ollama_options):
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=self.p["base_url"], **ollama_options)

    def describe_image(self, model, prompt, png, max_tokens):
        resp = self._client().chat(
            model=model,
            messages=[{"role": "user", "content": prompt, "images": [png]}],
            think=False,
            keep_alive=limits.INDEX_KEEP_ALIVE,
            options=settings.ollama_options(num_predict=max_tokens, num_ctx=4096, temperature=0),
        )
        return " ".join(resp.message.content.split())

    def list_models(self):
        client = self._client(timeout=10)
        out = []
        for m in client.list().models:
            try:
                caps = client.show(m.model).capabilities or []
                vision, tools = "vision" in caps, "tools" in caps
            except Exception as e:
                log.debug("capabilities of %s: %s", m.model, e)
                vision = tools = None  # the list still works; the app just can't grey out unfit models
            out.append({"id": m.model, "size": m.size, "vision": vision, "tools": tools})
        return sorted(out, key=lambda m: m["id"])


class OpenAICompatible(Backend):
    def _client(self):
        import openai

        return openai.OpenAI(
            base_url=self.p["base_url"], api_key=self.p.get("api_key") or "not-needed", timeout=120, max_retries=1
        )

    def chat_model(self, model, **ollama_options):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            base_url=self.p["base_url"],
            api_key=self.p.get("api_key") or "not-needed",
            temperature=ollama_options.get("temperature", 0),
            timeout=120,
            max_retries=1,
        )

    def describe_image(self, model, prompt, png, max_tokens):
        import openai

        url = "data:image/png;base64," + base64.b64encode(png).decode()
        try:
            resp = self._client().chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}],
                    }
                ],
                max_tokens=max_tokens,
                temperature=0,
            )
        except (openai.APIConnectionError, openai.AuthenticationError) as e:
            raise ConnectionError(why(e)) from e
        return " ".join((resp.choices[0].message.content or "").split())

    def list_models(self):
        try:
            models = self._client().models.list()
        except Exception as e:
            raise ConnectionError(why(e)) from e
        return sorted(
            ({"id": m.id, "size": None, "vision": None, "tools": None} for m in models), key=lambda m: m["id"]
        )


def backend(pid: str) -> Backend:
    p = registry.get(pid)
    return OllamaBackend(p) if p["kind"] == "ollama" else OpenAICompatible(p)


# ---------- what the rest of Lumen calls ----------


def chat_model(provider: str | None = None, model: str | None = None, **ollama_options):
    """The chat model for the agent job (or the given provider/model)."""
    return backend(provider or settings.agent_provider).chat_model(model or settings.agent_model, **ollama_options)


def describe_image(
    prompt: str, png: bytes, max_tokens: int = 200, provider: str | None = None, model: str | None = None
) -> str:
    """One image + prompt to the images-and-video model (or the given provider/model); the reply on
    one line. Raises ConnectionError when the provider can't be reached (indexing then stops that pass)."""
    return backend(provider or settings.vision_provider).describe_image(
        model or settings.caption_model, prompt, png, max_tokens
    )


def list_models(pid: str) -> list[dict]:
    return backend(pid).list_models()


def test(pid: str) -> dict:
    """Can we reach the provider? {ok, message} for the app."""
    try:
        n = len(list_models(pid))
        return {"ok": True, "message": f"Connected · {n} model{'s' if n != 1 else ''} available"}
    except Exception as e:
        log.info("provider %s test failed: %s", pid, e)
        return {"ok": False, "message": why(e)}
