"""Image search, similar images, photo uploads, thumbnails, and opening files."""

import io

import numpy as np
import pytest
from conftest import index_now, sse, tool_call
from PIL import Image

COLOURS = {"red": (220, 30, 30), "green": (30, 200, 40), "blue": (30, 40, 220)}


def _picture(colour: str, size=(160, 120), seed=0) -> Image.Image:
    rgb = np.array(COLOURS[colour], dtype=float)
    noise = np.random.default_rng(seed).normal(0, 20, (size[1], size[0], 3))
    return Image.fromarray(np.clip(rgb + noise, 0, 255).astype("uint8"))


@pytest.fixture
def pictures(env, fake_clip):
    """Images of three colours (and a smaller copy of the red one), indexed with the colour-only fake CLIP."""
    folder = env.downloads / "pictures"
    folder.mkdir()
    files = {}
    for i, colour in enumerate(COLOURS):
        files[colour] = folder / f"{colour}-car.jpg"
        _picture(colour, seed=i).save(files[colour], quality=95)
    files["red-copy"] = folder / "red-car-small.jpg"
    _picture("red", size=(80, 60), seed=7).save(files["red-copy"], quality=95)
    stats = index_now()
    assert stats["visual"]["images"] == 5  # these four and the grey sample holiday.png
    return files


def names(hits):
    return [h["name"] for h in hits]


def test_search_images_by_what_they_show(pictures, local):
    hits = local.get("/api/images/search", params={"q": "a red car"}).json()
    assert set(names(hits)[:2]) == {"red-car.jpg", "red-car-small.jpg"}
    assert "blue-car.jpg" not in names(hits)


def test_similar_images(pictures, local):
    hits = local.get("/api/images/similar", params={"path": str(pictures["red"])}).json()
    assert names(hits) == ["red-car-small.jpg"]  # itself left out, other colours too different


def test_find_similar_from_the_app_is_kept_in_the_chat_and_numbered(pictures, local, model):
    chat = local.post("/api/chats", json={}).json()["id"]
    hits = local.post(f"/api/chats/{chat}/similar", json={"path": str(pictures["blue"])}).json()
    assert names(hits) == []  # nothing else is blue
    hits = local.post(f"/api/chats/{chat}/similar", json={"path": str(pictures["red"])}).json()
    assert names(hits) == ["red-car-small.jpg"]
    history = local.get(f"/api/chats/{chat}/events").json()
    assert [e["type"] for e in history][-2:] == ["user", "results"]
    assert history[-2]["text"] == "Images like red-car.jpg"
    # "open the first one" now means the first of these results
    model.script = [tool_call("open_file", target="1")]
    events = sse(local.post(f"/api/chats/{chat}/messages", json={"text": "open the first one"}))
    [opened] = [e for e in events if e["type"] == "opened"]
    assert opened["path"] == str(pictures["red-copy"])


def test_a_dropped_photo_finds_look_alikes_and_is_kept(pictures, local):
    chat = local.post("/api/chats", json={}).json()["id"]
    buf = io.BytesIO()
    _picture("red", seed=42).save(buf, "PNG")
    hits = local.post(f"/api/chats/{chat}/similar-upload", content=buf.getvalue()).json()
    assert set(names(hits)) == {"red-car.jpg", "red-car-small.jpg"}
    upload = local.get(f"/api/chats/{chat}/events").json()[-2]["upload"]
    r = local.get(f"/api/uploads/{upload}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


def test_uploads_must_be_images(pictures, local):
    chat = local.post("/api/chats", json={}).json()["id"]
    assert local.post(f"/api/chats/{chat}/similar-upload", content=b"not an image").status_code == 400
    assert local.post(f"/api/chats/{chat}/similar-upload", content=b"").status_code == 400
    assert local.get("/api/uploads/../../etc").status_code in (400, 404)
    assert local.get("/api/uploads/abc-def").status_code == 400


def test_similar_needs_an_existing_chat(pictures, local):
    assert local.post("/api/chats/nope/similar", json={"path": str(pictures["red"])}).status_code == 404


@pytest.mark.parametrize("key", ["image", "pdf"])
def test_thumbnails_for_images_and_pdfs(indexed, local, key):
    r = local.get("/api/thumb", params={"path": str(indexed.files[key]), "w": 200})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).width <= 200


def test_no_thumbnail_for_text_files(indexed, local):
    assert local.get("/api/thumb", params={"path": str(indexed.files["notes"])}).status_code == 404


def test_files_outside_indexed_folders_are_off_limits(indexed, local, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    for path in ("/api/thumb", "/api/file"):
        assert local.get(path, params={"path": str(outside)}).status_code == 403
    assert local.post("/api/open", json={"path": str(outside)}).status_code == 403
    assert local.get("/api/thumb", params={"path": str(indexed.documents / "missing.png")}).status_code == 404


def test_open_and_show_in_test_mode_report_instead(indexed, local):
    r = local.post("/api/open", json={"path": str(indexed.files["pdf"])}).json()
    assert r["ok"] is True and r["message"].startswith("NOT OPENED") and "invoice-1042.pdf" in r["message"]
    r = local.post("/api/show", json={"path": str(indexed.files["pdf"])}).json()
    assert str(indexed.documents) in r["message"]


def test_scripts_open_their_folder_instead_of_running(indexed, local):
    script = indexed.documents / "cleanup.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o755)
    message = local.post("/api/open", json={"path": str(script)}).json()["message"]
    assert message.startswith("Scripts and programs open their folder instead")
    assert "cleanup.sh" not in message.split("Would have opened:")[1]
