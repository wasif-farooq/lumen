"""Speech to text with faster-whisper on the CPU (the GPU stays free for the chat model). The model
is loaded once and kept, so each utterance costs only its transcription (tiny: ~0.2 s for 3 s)."""

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..core.settings import settings
from ..indexing import power

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

_model: "WhisperModel | None" = None
_model_size = ""
_lock = threading.Lock()


def load() -> None:
    """Load the speech model now (a voice connection opens), not on the first utterance."""
    global _model, _model_size
    with _lock:
        if _model is None or _model_size != settings.voice_stt_model:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                settings.voice_stt_model,
                device="cpu",
                compute_type="int8",
                cpu_threads=power.threads(),
                download_root=str(settings.data_dir / "models"),
            )
            _model_size = settings.voice_stt_model
            log.info("speech model whisper-%s loaded", _model_size)


def transcribe(audio: np.ndarray) -> str:
    """What was said in 16 kHz mono float32 audio ("" for noise or silence)."""
    load()
    assert _model is not None
    segments, _info = _model.transcribe(audio, beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()
