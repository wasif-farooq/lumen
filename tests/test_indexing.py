"""Indexing: what gets indexed, updates, removals, excluded paths and paused folders."""

import os
import time

from conftest import OPEN_INDEX_CODE, index_now


def names(client, q, **params):
    return sorted(h["name"] for h in client.get("/api/search", params={"q": q, **params}).json())


def test_indexes_every_sample_file_and_reads_document_text(env, local):
    stats = index_now()
    assert stats["scanned"] == 6
    assert stats["added"] == 6
    assert stats["with_text"] == 5  # all but the image
    assert names(local, "invoice") == ["invoice-1042.pdf"]  # PDF text
    assert names(local, "library card") == ["library-letter.docx"]  # Word text
    assert names(local, "lentils") == ["lentil-soup.md"]  # plain text
    assert names(local, "holiday") == ["holiday.png"]  # by file name


def test_second_run_only_does_new_work(indexed):
    stats = index_now()
    assert (stats["added"], stats["updated"], stats["removed"]) == (0, 0, 0)


def test_changed_file_is_reindexed(indexed, local):
    notes = indexed.files["notes"]
    notes.write_text("Holiday planning: ferry tickets and a tent.\n")
    future = time.time() + 5
    os.utime(notes, (future, future))
    stats = index_now()
    assert stats["updated"] == 1
    assert names(local, "ferry") == ["budget-notes.txt"]
    assert names(local, "printer") == []


def test_deleted_file_drops_out(indexed, local):
    indexed.files["recipe"].unlink()
    assert index_now()["removed"] == 1
    assert names(local, "lentils") == []


def test_hidden_files_and_dependency_folders_are_skipped(env, local):
    (env.documents / ".secret.txt").write_text("hidden budget")
    (env.documents / "node_modules").mkdir()
    (env.documents / "node_modules" / "lib.txt").write_text("dependency budget")
    index_now()
    assert names(local, "budget") == ["budget-notes.txt"]


def test_excluded_file_is_removed_and_stays_out(indexed, local):
    path = str(indexed.files["pdf"])
    r = local.post("/api/index/exclude", json={"path": path})
    assert r.status_code == 200 and r.json()["removed"] == 1
    assert names(local, "invoice") == []
    index_now()
    assert names(local, "invoice") == []
    assert path in local.get("/api/settings").json()["excluded"]


def test_excluded_folder_and_include_again(indexed, local):
    old = str(indexed.documents / "old")
    assert local.post("/api/index/exclude", json={"path": old}).json()["removed"] == 1
    index_now()
    assert names(local, "membership") == []
    assert local.post("/api/index/include", json={"path": old, "reindex": False}).status_code == 200
    index_now()
    assert names(local, "membership") == ["annual-report.txt"]


def test_exclude_is_refused_outside_indexed_folders_and_for_a_whole_root(indexed, local, tmp_path):
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    assert local.post("/api/index/exclude", json={"path": str(outside)}).status_code == 400
    assert local.post("/api/index/exclude", json={"path": str(indexed.documents)}).status_code == 400


def test_paused_folder_keeps_its_files_but_is_not_rescanned(indexed, local):
    downloads = str(indexed.downloads.resolve())
    assert local.post("/api/folders/pause", json={"path": downloads}).json() == {"paused": True}
    indexed.files["recipe"].unlink()
    (indexed.downloads / "new-file.txt").write_text("brand new lentils")
    index_now()
    assert names(local, "lentils") == ["lentil-soup.md"]  # kept, not rescanned
    folders = {f["path"]: f for f in local.get("/api/status").json()["folders"]}
    assert folders[downloads]["paused"] is True
    assert local.post("/api/folders/resume", json={"path": downloads, "reindex": False}).json() == {"paused": False}
    index_now()
    assert names(local, "lentils") == ["new-file.txt"]


def test_clear_folder_removes_its_index_entries_only(indexed, local):
    downloads = str(indexed.downloads.resolve())
    r = local.post("/api/folders/clear", json={"path": downloads, "reindex": False})
    assert r.json()["removed"] == 2
    assert names(local, "lentils") == []
    assert names(local, "invoice") == ["invoice-1042.pdf"]
    assert indexed.files["recipe"].exists()  # the file itself is untouched


def test_folder_actions_need_an_indexed_folder(indexed, local, tmp_path):
    assert local.post("/api/folders/pause", json={"path": str(tmp_path)}).status_code == 404


def test_folder_changes_are_refused_while_indexing_runs(indexed, local, indexer, monkeypatch):
    with monkeypatch.context() as m:
        indexer.pretend_running(m)
        r = local.post("/api/folders/pause", json={"path": str(indexed.downloads.resolve())})
    assert r.status_code == 409


def test_a_new_index_can_be_opened_by_several_processes_at_once(env):
    """The server and the indexer open a fresh database at the same time on first run."""
    import subprocess
    import sys

    procs = [subprocess.Popen([sys.executable, "-c", OPEN_INDEX_CODE], stderr=subprocess.PIPE) for _ in range(12)]
    errors = [p.communicate()[1].decode() for p in procs if p.wait() != 0]
    assert errors == []


def test_an_index_from_0_1_loses_the_unused_image_hash_columns_and_keeps_its_files(env):
    import sqlite3
    import subprocess
    import sys

    from conftest import index_file

    old = sqlite3.connect(index_file())
    old.executescript(
        "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL, ext TEXT NOT NULL,"
        " size INTEGER NOT NULL, mtime REAL NOT NULL, has_text INTEGER NOT NULL DEFAULT 0, caption TEXT,"
        " duration REAL, media_done INTEGER, fingerprint TEXT, embedding BLOB, dhash INTEGER, sha1 TEXT,"
        " visual_done INTEGER);"
        "INSERT INTO files (path, name, ext, size, mtime, caption, dhash, sha1)"
        " VALUES ('/x/a.png', 'a.png', 'png', 1, 0, 'a red bicycle', 7, 'ab');"
    )
    old.commit()
    old.close()

    # Opened the way the app and the indexer open it (in another process, as they do)
    subprocess.run([sys.executable, "-c", OPEN_INDEX_CODE], check=True)

    conn = sqlite3.connect(index_file())
    columns = {r[1] for r in conn.execute("PRAGMA table_info(files)")}
    assert "dhash" not in columns and "sha1" not in columns
    assert {"embedding", "visual_done", "caption"} <= columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1
    assert conn.execute("SELECT name, caption FROM files").fetchall() == [("a.png", "a red bicycle")]


def test_a_new_index_starts_at_the_latest_schema_version(env):
    import sqlite3

    from conftest import index_file

    index_now()
    conn = sqlite3.connect(index_file())
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1
    assert "dhash" not in {r[1] for r in conn.execute("PRAGMA table_info(files)")}
