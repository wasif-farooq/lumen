"""What is said in video and audio: faster-whisper transcripts with timestamps, on the CPU so the
GPU stays free for the language model."""

import logging
import subprocess
from typing import TYPE_CHECKING

from ...core.settings import settings
from .. import power

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


# ---------- layer 3: what is said ----------

_whisper = None


def load_whisper() -> "WhisperModel":
    """Load (downloading on first use) the speech model. Runs on CPU so the GPU stays free for the LLM."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        _whisper = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=power.threads(),
            download_root=str(settings.data_dir / "models"),
        )
    return _whisper


def transcribe(path: str) -> tuple[list[tuple[float, float, str]], str]:
    """Return ([(start, end, text), ...], language)."""
    import numpy as np

    # Decode with ffmpeg ourselves (16 kHz mono float32): faster-whisper's own PyAV decoding
    # breaks with PyAV >= 19, and ffmpeg handles more containers anyway.
    pcm = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-threads",
            str(power.threads()),
            "-i",
            path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        timeout=3600,
    ).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    if audio.size == 0:
        return [], ""
    # temperature=0 only: no slow re-decoding passes on hard audio (saves CPU/battery)
    segments, info = load_whisper().transcribe(
        audio, vad_filter=True, beam_size=1, condition_on_previous_text=False, temperature=0.0
    )
    if info.language_probability < 0.6:
        return [], ""  # noise/music, not speech: whisper only produces junk here
    return [
        (s.start, s.end, s.text.strip())
        for s in segments
        if s.text.strip() and s.no_speech_prob < 0.8 and any(ch.isalnum() for ch in s.text)
    ], info.language
