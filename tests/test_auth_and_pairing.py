"""Who may do what: the laptop itself, a paired phone, and anyone else on the network."""

import pytest

LOCAL_ONLY = [
    ("put", "/api/settings", {"threads": 2}),
    ("post", "/api/index/exclude", {"path": "/x"}),
    ("post", "/api/folders/clear", {"path": "/x"}),
    ("post", "/api/providers", {"kind": "openai", "base_url": "http://x"}),
    ("put", "/api/roles", {"role": "speech", "model": "base"}),
    ("post", "/api/models/check", {"role": "agent", "provider": "ollama", "model": "m"}),
    ("post", "/api/pair/start", None),
    ("get", "/api/devices", None),
]


def call(client, method, path, body=None, **kw):
    return getattr(client, method)(path, **({"json": body} if body is not None else {}), **kw)


def pair(local, remote, name="Pixel") -> str:
    code = local.post("/api/pair/start").json()["code"]
    r = remote.post("/api/pair", json={"code": code, "name": name})
    assert r.status_code == 200
    return r.json()["token"]


def test_hello_needs_no_pairing(env, remote):
    assert remote.get("/api/hello").json()["app"] == "lumen"


def test_unpaired_devices_get_nothing(env, remote):
    assert remote.get("/api/status").status_code == 401
    assert remote.get("/api/search", params={"q": "x"}).status_code == 401
    assert remote.get("/api/status", headers={"Authorization": "Bearer made-up"}).status_code == 401


@pytest.mark.parametrize("method,path,body", LOCAL_ONLY)
def test_settings_and_keys_only_from_the_laptop(env, local, remote, method, path, body):
    token = pair(local, remote)
    r = call(remote, method, path, body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_a_paired_phone_can_search_and_chat(indexed, local, remote):
    token = pair(local, remote)
    auth = {"Authorization": f"Bearer {token}"}
    assert remote.get("/api/status", headers=auth).status_code == 200
    assert remote.get("/api/search", params={"q": "invoice"}, headers=auth).json()[0]["name"] == "invoice-1042.pdf"
    assert remote.post("/api/chats", json={}, headers=auth).status_code == 200


def test_pairing_codes_are_single_use(env, local, remote):
    code = local.post("/api/pair/start").json()["code"]
    assert remote.post("/api/pair", json={"code": code}).status_code == 200
    assert remote.post("/api/pair", json={"code": code}).status_code == 403


def test_wrong_codes_are_refused_and_limited(env, local, remote):
    code = local.post("/api/pair/start").json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert remote.post("/api/pair", json={"code": wrong}).status_code == 403
    assert remote.post("/api/pair", json={"code": code}).status_code == 403  # too many tries


def test_unpairing_revokes_the_token(env, local, remote):
    token = pair(local, remote, name="Old phone")
    [device] = local.get("/api/devices").json()
    assert device["name"] == "Old phone" and "token_sha256" not in device
    local.delete(f"/api/devices/{device['id']}")
    assert remote.get("/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_tokens_are_stored_hashed(env, local, remote):
    token = pair(local, remote)
    assert token not in (env.data / "devices.json").read_text()


def test_paired_devices_are_stored_readable_only_by_the_user(env, local, remote):
    import stat

    code = local.post("/api/pair/start").json()["code"]
    assert remote.post("/api/pair", json={"code": code, "name": "phone"}).status_code == 200
    devices = env.data / "devices.json"
    assert stat.S_IMODE(devices.stat().st_mode) == 0o600
    assert "token" not in devices.read_text().replace("token_sha256", "")  # only a hash of the token
