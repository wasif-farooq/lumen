"""The `lumen` command line (run as a real subprocess, like a user would)."""

import json
import subprocess
import sys


def lumen(*args, env_extra=None) -> subprocess.CompletedProcess:
    import os

    return subprocess.run([sys.executable, "-m", "lumen", *args], capture_output=True, text=True,
                          env={**os.environ, "COLUMNS": "200", **(env_extra or {})}, timeout=120)


def test_help_lists_the_commands(env):
    out = lumen("--help").stdout
    for cmd in ("index", "stats", "search", "ask", "chat", "serve"):
        assert cmd in out


def test_index_then_search_and_stats(env):
    r = lumen("index")
    assert r.returncode == 0, r.stderr
    assert "Files done" in r.stdout and "added 6" in r.stdout
    out = lumen("search", "invoice").stdout
    assert "1. invoice-1042.pdf" in out and "match:" in out
    assert "No results." in lumen("search", "zeppelin").stdout
    assert "'files': 6" in lumen("stats").stdout


def test_search_filters(env):
    lumen("index")
    out = lumen("search", "--ext", "md").stdout
    assert "lentil-soup.md" in out and "invoice" not in out


def test_index_progress_events_for_the_app(env):
    """With LUMEN_EVENTS set, the indexer also prints '@@{json}' lines the server turns into progress."""
    r = lumen("index", env_extra={"LUMEN_EVENTS": "1"})
    events = [json.loads(line[2:]) for line in r.stdout.splitlines() if line.startswith("@@")]
    phases = [e["phase"] for e in events if "phase" in e]
    assert phases == ["scan", "passages"]  # AI passes are skipped in saver mode
    assert events[-1]["summary"]["added"] == 6
