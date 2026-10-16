"""Errors the app can show, and logs that explain them."""

import subprocess
import sys

from conftest import add_route, raise_error, wait_until
from fastapi.testclient import TestClient


def test_errors_have_one_shape_with_a_request_id(local):
    r = local.post("/api/chats/nope/messages", json={"text": "hi"})
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] == "No such chat"  # what older apps read
    assert body["error"]["code"] == "not_found" and body["error"]["message"] == "No such chat"
    assert body["error"]["id"] == r.headers["x-request-id"]


def test_typed_errors_carry_a_hint(env, local):
    add_route(env.app, "/test/hint", lambda: raise_error("Conflict", "Busy", "Try again in a minute"))
    r = local.get("/test/hint")
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "conflict",
        "message": "Busy",
        "hint": "Try again in a minute",
        "id": r.headers["x-request-id"],
    }


def test_who_may_ask_errors(remote):
    r = remote.get("/api/status")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_paired"
    r = remote.post("/api/pair", json={"code": "000000", "name": "phone"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_code"


def test_settings_from_a_phone_are_refused_as_local_only(local, remote):
    token = local.post("/api/pair/start").json()["code"]
    phone = remote.post("/api/pair", json={"code": token, "name": "phone"}).json()["token"]
    r = remote.put("/api/settings", json={"power_mode": "saver"}, headers={"Authorization": f"Bearer {phone}"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "local_only"


def test_paths_outside_the_folders(local):
    r = local.get("/api/file", params={"path": "/etc/passwd"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "outside_folders"


def test_validation_errors_keep_fastapis_detail(local):
    r = local.post("/api/chats/x/messages", json={})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert r.json()["error"]["code"] == "invalid_input" and "text" in r.json()["error"]["message"]


def test_a_crash_answers_500_with_an_id_and_logs_the_traceback(env, logs):
    def boom():
        raise RuntimeError("secret internal detail")

    add_route(env.app, "/test/boom", boom)
    r = TestClient(env.app, client=("127.0.0.1", 50000)).get("/test/boom")
    assert r.status_code == 500
    rid = r.json()["error"]["id"]
    assert rid and rid == r.headers["x-request-id"]
    assert "secret internal detail" not in r.text  # details stay in the log
    assert f"id {rid}" in r.json()["error"]["message"]
    log = (logs / "lumen.log").read_text()
    assert f"[{rid}]" in log and "RuntimeError: secret internal detail" in log and "Traceback" in log


def test_requests_are_logged_with_their_id(local, logs):
    r = local.get("/api/status")
    log = (logs / "lumen.log").read_text()
    assert f"[{r.headers['x-request-id']}] GET /api/status 200" in log


def test_a_failed_chat_turn_is_logged(local, logs, model):
    model.script = [RuntimeError("model fell over")]
    chat = local.post("/api/chats", json={}).json()["id"]
    events = local.post(f"/api/chats/{chat}/messages", json={"text": "hello"}).text
    assert '"type": "error"' in events
    log = (logs / "lumen.log").read_text()
    assert "the turn failed" in log and "RuntimeError: model fell over" in log


def test_an_index_run_that_crashes_shows_an_error(local, monkeypatch, tmp_path):
    monkeypatch.setenv("LUMEN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LUMEN_NUM_CTX", "lots")  # the indexer can't start with this
    local.post("/api/index")
    wait_until(lambda: not local.get("/api/index").json()["running"])
    error = local.get("/api/index").json()["error"]
    assert error and "Indexing stopped unexpectedly" in error and "indexer.log" in error


def test_a_stopped_index_run_is_not_an_error(local, indexer):
    local.post("/api/index")
    local.post("/api/index/stop")
    wait_until(lambda: not local.get("/api/index").json()["running"])
    assert local.get("/api/index").json()["error"] is None


def test_the_cli_writes_its_own_log(env, tmp_path):
    import os

    folder = tmp_path / "logs"
    r = subprocess.run(
        [sys.executable, "-m", "lumen", "index"],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "LUMEN_LOG_DIR": str(folder)},
    )
    assert r.returncode == 0, r.stderr
    assert "index run done" in (folder / "indexer.log").read_text()


def test_diagnostics_for_a_bug_report(local, remote, logs):
    local.post(
        "/api/providers",
        json={
            "id": "cloud",
            "kind": "openai",
            "name": "Cloud",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-secret-123",
        },
    )
    local.get("/api/status")
    r = local.get("/api/diagnostics")
    d = r.json()
    assert d["log_dir"] == str(logs) and d["version"] and d["roles"]["agent"]["model"]
    assert any("GET /api/status 200" in line for line in d["logs"]["server"])
    assert "sk-secret-123" not in r.text
    assert remote.get("/api/diagnostics").status_code in (401, 403)
