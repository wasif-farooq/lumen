"""Index runs started from the app: the indexer subprocess, progress, pause, resume and stop."""

import time

from fastapi.testclient import TestClient

from conftest import app, index_now, wait_until


def progress(client) -> dict:
    return client.get("/api/index").json()


def many_files(env, n=2500):
    folder = env.documents / "many"
    folder.mkdir()
    for i in range(n):
        (folder / f"note-{i}.txt").write_text(f"note number {i}")


def test_a_run_from_the_app_indexes_and_reports_a_summary(env, local):
    assert local.post("/api/index").json() == {"running": True}
    assert wait_until(lambda: not progress(local)["running"])
    p = progress(local)
    assert p["summary"]["scanned"] == 6
    assert p["phase"] == "passages"  # the last pass
    assert any("Files done" in line for line in p["lines"])  # the human-readable log
    assert local.get("/api/search", params={"q": "invoice"}).json()


def test_pause_holds_the_run_and_resume_finishes_it(env, local):
    many_files(env)
    local.post("/api/index")
    local.post("/api/index/pause")
    assert wait_until(lambda: progress(local)["paused"])
    held = progress(local)["scanned"]
    assert progress(local)["pausing"] is False
    time.sleep(1)  # stays held
    assert progress(local)["scanned"] == held
    local.post("/api/index/resume")
    assert wait_until(lambda: not progress(local)["running"])
    assert progress(local)["summary"]["scanned"] == 6 + 2500
    assert not (env.data / "index.pause").exists()


def test_stop_ends_the_run_and_keeps_finished_work(env, local):
    many_files(env)
    local.post("/api/index")
    local.post("/api/index/pause")
    assert wait_until(lambda: progress(local)["paused"])
    r = local.post("/api/index/stop").json()
    assert r == {"stopped": True, "running": False}
    assert any(line.startswith("Stopped.") for line in progress(local)["lines"])


def test_starting_twice_runs_once(env, local):
    local.post("/api/index")
    local.post("/api/index")
    assert wait_until(lambda: not progress(local)["running"])
    assert progress(local)["summary"]["added"] == 6


def test_server_shutdown_stops_a_running_index(env, indexer):
    many_files(env, 4000)
    with TestClient(app(), client=("127.0.0.1", 50000)) as client:
        client.post("/api/index")
        client.post("/api/index/pause")
        assert wait_until(lambda: progress(client)["paused"])
        proc = indexer.process
    assert proc.poll() is not None  # shutdown ended the indexer process


def test_status_shows_indexing_and_paused(env, local):
    many_files(env)
    local.post("/api/index")
    local.post("/api/index/pause")
    assert wait_until(lambda: local.get("/api/status").json()["index_paused"])
    assert local.get("/api/status").json()["indexing"] is True


def test_pause_also_holds_a_rescan_where_nothing_changed(env, local):
    many_files(env)
    index_now()  # everything already indexed: the next run only re-checks
    local.post("/api/index")
    local.post("/api/index/pause")
    assert wait_until(lambda: progress(local)["paused"])
    local.post("/api/index/resume")
    assert wait_until(lambda: not progress(local)["running"])
    assert progress(local)["summary"]["added"] == 0
