"""Where an utterance starts and ends in a stream of microphone audio (PCM16, mono, 16 kHz).

A voice detector (Silero) scores each 32 ms window. Speech starts after two windows that are
clearly speech; the utterance ends after ~0.7 s that clearly isn't (two thresholds, so it doesn't
flicker on soft syllables), and is cut off at a maximum length. A little audio from before the
start is kept, so the first syllable isn't clipped.

Loudness alone wasn't enough: audio that starts with digital silence, or a phone's noise
suppression between words, pulls any estimate of the room's level down until ordinary noise
looks like speech, and an utterance never ends."""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import vad

RATE = 16_000
WINDOW = vad.WINDOW  # 32 ms
START_PROB, END_PROB = 0.5, 0.35
START_WINDOWS = 2  # 64 ms of speech: it has started
END_WINDOWS = 22  # ~0.7 s without speech: the utterance is over
PRE_ROLL = 10  # ~0.3 s kept from before the start
MAX_SECONDS = 30

Detector = Callable[[np.ndarray], float]


@dataclass
class Endpointer:
    detector: Detector = field(default_factory=lambda: vad.SileroStream())
    _pending: bytes = b""
    _windows: list[np.ndarray] = field(default_factory=list)  # the utterance so far (or pre-roll)
    _loud: int = 0
    _quiet: int = 0
    speaking: bool = False

    def feed(self, pcm16: bytes) -> list[str | np.ndarray]:
        """Add audio; returns what happened: "speech_start", and each finished utterance (float32)."""
        events: list[str | np.ndarray] = []
        data = self._pending + pcm16
        whole = len(data) - len(data) % (WINDOW * 2)
        self._pending = data[whole:]
        for i in range(0, whole, WINDOW * 2):
            window = np.frombuffer(data[i : i + WINDOW * 2], np.int16).astype(np.float32) / 32768
            events += self._window(window)
        return events

    def flush(self) -> np.ndarray | None:
        """End the utterance now (push-to-talk released); None when nothing was said."""
        audio = np.concatenate(self._windows) if self.speaking and self._windows else None
        self._reset()
        return audio

    def _window(self, window: np.ndarray) -> list[str | np.ndarray]:
        p = self.detector(window)
        self._windows.append(window)
        if not self.speaking:
            self._loud = self._loud + 1 if p >= START_PROB else 0
            del self._windows[: -(PRE_ROLL + START_WINDOWS)]
            if self._loud >= START_WINDOWS:
                self.speaking, self._quiet = True, 0
                return ["speech_start"]
            return []
        self._quiet = self._quiet + 1 if p < END_PROB else 0
        if self._quiet >= END_WINDOWS or len(self._windows) * WINDOW >= MAX_SECONDS * RATE:
            audio = np.concatenate(self._windows[: len(self._windows) - self._quiet + 3])  # keep ~0.1 s of tail
            self._reset()
            return [audio]
        return []

    def _reset(self) -> None:
        self._windows, self._loud, self._quiet, self.speaking = [], 0, 0, False
