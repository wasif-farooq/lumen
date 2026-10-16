"""Text to speech. One backend today, Piper (fast on the CPU: a sentence's first audio in ~0.1 s);
the voice is downloaded into the data folder the first time it is used.

Piper is GPL-3.0 and an optional extra (`uv sync --extra voice`): see docs/VOICE.md."""

import logging
import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from ..core import errors
from ..core.settings import settings

log = logging.getLogger(__name__)

VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


class Speaker(Protocol):
    sample_rate: int

    def speak(self, text: str) -> Iterator[bytes]:
        """PCM16 mono audio for the text, in pieces as they are made."""
        ...


def _require_piper() -> None:
    try:
        import piper  # noqa: F401
    except ImportError as e:
        raise errors.VoiceUnavailable(
            "Voice chat needs its speech engine, which isn't installed.",
            "Install it with: uv sync --extra voice",
        ) from e


class PiperSpeaker:
    def __init__(self, model: Path) -> None:
        from piper import PiperVoice

        self.voice = PiperVoice.load(str(model))
        self.sample_rate = self.voice.config.sample_rate

    def speak(self, text: str) -> Iterator[bytes]:
        for chunk in self.voice.synthesize(text):
            yield chunk.audio_int16_bytes


_speaker: Speaker | None = None
_voice_name = ""
_lock = threading.Lock()


def load() -> Speaker:
    """The speaker for the configured voice, loaded once (and downloaded the first time)."""
    global _speaker, _voice_name
    with _lock:
        if _speaker is None or _voice_name != settings.voice_tts_voice:
            _require_piper()  # before downloading a voice it couldn't use
            _speaker = PiperSpeaker(_voice_file(settings.voice_tts_voice))
            _voice_name = settings.voice_tts_voice
            log.info("voice %s loaded", _voice_name)
        return _speaker


def _voice_file(name: str) -> Path:
    """The voice model, e.g. en_US-lessac-medium: downloaded from the Piper voices repository."""
    folder = settings.data_dir / "models" / "piper"
    model = folder / f"{name}.onnx"
    if model.exists() and model.with_suffix(".onnx.json").exists():
        return model
    try:
        lang, speaker, quality = name.split("-")
    except ValueError as e:
        raise errors.InvalidInput(f"Not a Piper voice name: {name}", "For example: en_US-lessac-medium") from e
    base = f"{VOICES_URL}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for suffix in (".onnx.json", ".onnx"):
            part = folder / f"{name}{suffix}.part"
            log.info("downloading voice %s%s", name, suffix)
            urllib.request.urlretrieve(f"{base}{suffix}", part)
            part.rename(folder / f"{name}{suffix}")
    except OSError as e:
        raise errors.VoiceUnavailable(f"Could not download the voice {name}.", "Check the internet connection.") from e
    return model
