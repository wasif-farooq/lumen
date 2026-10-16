"""Model providers, roles, API keys and the compatibility check."""

import json
import stat

import pytest
from conftest import tool_call


def add(client, **body):
    r = client.post("/api/providers", json={"kind": "openai", **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_ollama_is_built_in(env, local):
    data = local.get("/api/providers").json()
    [ollama] = data["providers"]
    assert ollama["id"] == "ollama" and ollama["builtin"] is True and ollama["cloud"] is False
    assert data["roles"]["agent"] == {"provider": "ollama", "model": "qwen3.5:2b"}
    assert "small" in data["speech_models"]


def test_api_key_is_stored_privately_and_never_returned(env, local):
    p = add(local, name="OpenRouter", base_url="https://openrouter.ai/api/v1", api_key="sk-or-secret-123456")
    assert p["has_key"] is True and p["key_hint"] == "…3456"
    assert "sk-or-secret" not in json.dumps(local.get("/api/providers").json())
    assert "sk-or-secret" not in json.dumps(local.get("/api/settings").json())
    keyfile = env.data / "providers.json"
    assert "sk-or-secret-123456" in keyfile.read_text()
    assert stat.S_IMODE(keyfile.stat().st_mode) == 0o600


def test_editing_without_a_key_keeps_the_saved_key(env, local):
    p = add(local, name="LM", base_url="http://localhost:1234/v1", api_key="key-abcdefgh")
    p2 = add(local, id=p["id"], name="LM Studio", base_url="http://localhost:1234/v1")
    assert p2["name"] == "LM Studio" and p2["has_key"] is True
    p3 = add(local, id=p["id"], name="LM Studio", base_url="http://localhost:1234/v1", clear_key=True)
    assert p3["has_key"] is False


@pytest.mark.parametrize(
    "url,cloud",
    [
        ("https://api.openai.com/v1", True),
        ("https://openrouter.ai/api/v1", True),
        ("http://localhost:1234/v1", False),
        ("http://127.0.0.1:8080/v1", False),
        ("http://192.168.1.20:8000/v1", False),
        ("http://10.0.0.5:8000", False),
    ],
)
def test_cloud_detection(env, local, url, cloud):
    assert add(local, name="X", base_url=url)["cloud"] is cloud


def test_invalid_provider_input_is_refused(env, local):
    assert local.post("/api/providers", json={"kind": "openai", "name": "x", "base_url": "ftp://x"}).status_code == 400
    assert local.post("/api/providers", json={"kind": "magic", "base_url": "http://x"}).status_code == 400


def test_roles_and_removal_rules(env, local):
    p = add(local, name="LM", base_url="http://localhost:1234/v1")
    roles = local.put("/api/roles", json={"role": "vision", "provider": p["id"], "model": "llava"}).json()
    assert roles["vision"] == {"provider": p["id"], "model": "llava"}
    assert local.delete(f"/api/providers/{p['id']}").status_code == 400  # in use
    local.put("/api/roles", json={"role": "vision", "provider": "ollama", "model": "qwen2.5vl:3b"})
    assert local.delete(f"/api/providers/{p['id']}").status_code == 200
    assert local.delete("/api/providers/ollama").status_code == 400  # built in
    assert local.put("/api/roles", json={"role": "speech", "model": "huge"}).status_code == 400
    assert local.put("/api/roles", json={"role": "speech", "model": "base"}).json()["speech"]["model"] == "base"
    assert local.put("/api/roles", json={"role": "agent", "provider": "nope", "model": "x"}).status_code == 404


def test_status_reports_cloud_chat(env, local):
    p = add(local, name="OpenAI", base_url="https://api.openai.com/v1", api_key="sk-test-00000000")
    local.put("/api/roles", json={"role": "agent", "provider": p["id"], "model": "gpt-mini"})
    models = local.get("/api/status").json()["models"]
    assert models["agent_provider"] == "OpenAI" and models["agent_cloud"] is True


def test_unreachable_provider_test_says_so(env, local):
    p = add(local, name="Nothing", base_url="http://127.0.0.1:9/v1")
    r = local.post(f"/api/providers/{p['id']}/test").json()
    assert r["ok"] is False and "connect" in r["message"].lower()


def test_check_passes_a_chat_model_that_calls_tools(env, local, model, ollama_caps):
    model.script = [tool_call("search_files", query="invoices")]
    ollama_caps(["completion", "tools"])
    r = local.post("/api/models/check", json={"role": "agent", "provider": "ollama", "model": "m"}).json()
    assert r["ok"] is True
    assert [c["name"] for c in r["checks"]] == ["Answers", "Calls tools"]


def test_check_fails_a_chat_model_that_answers_in_text(env, local, model, ollama_caps):
    from langchain_core.messages import AIMessage

    model.script = [AIMessage(content="Here are your invoices!")]
    ollama_caps(["completion", "tools"])
    r = local.post("/api/models/check", json={"role": "agent", "provider": "ollama", "model": "m"}).json()
    assert r["ok"] is False and "instead of calling the search tool" in r["checks"][-1]["detail"]


def test_check_uses_what_ollama_reports_a_model_can_do(env, local, ollama_caps):
    ollama_caps(["completion"])
    r = local.post("/api/models/check", json={"role": "vision", "provider": "ollama", "model": "m"}).json()
    assert r["ok"] is False and "can't see images" in r["checks"][0]["detail"]


def test_vision_check_reads_the_test_picture(env, local, ollama_caps, vision):
    ollama_caps(["vision"])
    vision.reply = "4721"
    r = local.post("/api/models/check", json={"role": "vision", "provider": "ollama", "model": "m"}).json()
    assert r["ok"] is True
    vision.reply = "a white box"
    assert (
        local.post("/api/models/check", json={"role": "vision", "provider": "ollama", "model": "m"}).json()["ok"]
        is False
    )


def test_listing_a_providers_models(env, local, provider_models):
    models = [{"id": "qwen3.5:2b", "size": 2_700_000_000, "vision": False, "tools": True}]
    provider_models(models)
    assert local.get("/api/providers/ollama/models").json() == models


def test_listing_models_of_a_provider_that_is_down_says_so(env, local):
    r = local.get("/api/providers/ollama/models")  # Ollama points at an address where nothing listens
    assert r.status_code == 502 and r.json()["error"]["code"] == "provider_unavailable"


def test_downloading_an_ollama_model_reports_its_progress(env, local):
    from conftest import wait_until

    r = local.post("/api/providers/ollama/pull", json={"model": "tiny:1b"})
    assert r.status_code == 200, r.text
    assert r.json()["model"] == "tiny:1b" and r.json()["done"] is False
    # Nothing listens at the test Ollama address: the download ends with an error the app shows
    wait_until(lambda: local.get("/api/providers").json()["pulls"][0]["done"])
    [pull] = local.get("/api/providers").json()["pulls"]
    assert pull["error"]
    assert local.post("/api/providers/ollama/pull", json={"model": " "}).status_code == 400
