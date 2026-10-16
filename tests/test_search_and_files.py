"""Search filters, file details, and the status summary."""

from conftest import OLD


def search(client, q="", **params):
    r = client.get("/api/search", params={"q": q, **params})
    assert r.status_code == 200
    return r.json()


def test_search_result_shape(indexed, local):
    [hit] = search(local, "invoice")
    assert hit["name"] == "invoice-1042.pdf"
    assert hit["kind"] == "pdf"
    assert "[Invoice]" in hit["snippet"]  # matches are marked for highlighting
    assert {"path", "ext", "size", "mtime"} <= hit.keys()


def test_filter_by_file_type(indexed, local):
    assert [h["name"] for h in search(local, "", ext="md")] == ["lentil-soup.md"]


def test_filter_by_dates(indexed, local):
    old = [h["name"] for h in search(local, "", before="2020-01-01")]
    assert old == ["annual-report.txt"]
    recent = [h["name"] for h in search(local, "", after="2020-01-01")]
    assert "annual-report.txt" not in recent and len(recent) == 5


def test_filter_by_folder(indexed, local):
    names = {h["name"] for h in search(local, "", folder="Downloads")}
    assert names == {"lentil-soup.md", "holiday.png"}


def test_file_details_include_the_indexed_text(indexed, local):
    info = local.get("/api/file", params={"path": str(indexed.files["docx"])}).json()
    assert info["indexed"] is True and info["searchable"] is True
    assert "library card renewal" in info["excerpt"]
    assert info["kind"] == "doc"


def test_file_details_for_a_missing_file(indexed, local):
    assert local.get("/api/file", params={"path": str(indexed.documents / "nope.txt")}).status_code == 404


def test_status_summarises_the_index(indexed, local):
    st = local.get("/api/status").json()
    assert st["index"]["files"] == 6
    assert st["index"]["with_text"] == 5
    assert st["indexing"] is False
    assert {f["files"] for f in st["folders"]} == {4, 2}
    assert st["last_index"]["stats"]["scanned"] == 6
    assert st["models"]["agent_provider"] == "Ollama"
    assert st["models"]["agent_cloud"] is False


def test_old_file_dates_are_kept(indexed, local):
    [hit] = search(local, "membership")
    assert abs(hit["mtime"] - OLD) < 2
