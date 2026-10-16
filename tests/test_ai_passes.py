"""The AI indexing passes with fake models: image descriptions, and video/audio (frames + speech)."""

import shutil
import subprocess

import pytest
from conftest import index_now

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def test_images_get_a_searchable_description(env, local, ai_on, vision, monkeypatch):
    ai_on(captions=True)
    stats = index_now()
    assert stats["captions"]["captioned"] == 1  # holiday.png (the PDF has a text layer)
    [hit] = local.get("/api/search", params={"q": "sports car"}).json()
    assert hit["name"] == "holiday.png"
    info = local.get("/api/file", params={"path": str(env.files["image"])}).json()
    assert info["caption"].startswith("A red sports car") and info["searchable"] is True
    assert index_now().get("captions", {}).get("captioned", 0) == 0  # not described twice


def test_a_failing_description_is_counted_and_not_retried(env, ai_on, vision, monkeypatch):
    ai_on(captions=True)
    vision.error = RuntimeError("model crashed")
    assert index_now()["captions"]["failed"] == 1
    vision.error = None
    assert index_now().get("captions", {}).get("captioned", 0) == 0


def test_unreachable_vision_model_skips_the_pass_with_a_message(env, ai_on, vision, monkeypatch):
    ai_on(captions=True)
    vision.error = ConnectionError("refused")
    stats = index_now()
    assert "not reachable" in stats["captions"]["error"]
    assert stats["added"] == 6  # files and their text are still indexed


def test_on_battery_saver_mode_skips_ai_work(env, vision, set_settings):
    set_settings(captions=True)  # wanted, but the power mode says no
    stats = index_now()
    assert stats["heavy_skipped"] == "power mode is 'saver'"
    assert vision.calls == 0


@pytest.fixture
def clip(env):
    """A 2-second video with sound."""
    path = env.downloads / "beach-trip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@needs_ffmpeg
def test_videos_get_frames_described_and_speech_searchable(env, local, ai_on, vision, speech, clip, monkeypatch):
    ai_on(media=True, transcripts=True)
    vision.reply = "Home video of a beach with waves. Text: none"
    m = index_now()["media"]
    assert (m["media"], m["described"], m["transcribed"], m["failed"]) == (1, 1, 1, 0)

    [hit] = local.get("/api/search", params={"q": "last train"}).json()
    assert hit["name"] == "beach-trip.mp4" and hit["kind"] == "video"
    assert hit["at"] == 605.65 and hit["at_text"].startswith("What time does the last train")
    assert local.get("/api/search", params={"q": "beach waves"}).json()[0]["name"] == "beach-trip.mp4"

    info = local.get("/api/file", params={"path": str(clip), "at": 605}).json()
    assert [s["time"] for s in info["segments"]] == ["10:00", "10:05"]
    assert info["duration"] == pytest.approx(2.0, abs=0.2)


@needs_ffmpeg
def test_an_identical_copy_of_a_video_reuses_the_work(env, ai_on, vision, speech, clip, monkeypatch):
    ai_on(media=True, transcripts=True)
    shutil.copy2(clip, env.documents / "beach-trip-copy.mp4")
    m = index_now()["media"]
    assert m["media"] == 1 and m["reused"] == 1 and vision.calls == 1
