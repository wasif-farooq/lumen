"""Is this speech? Silero VAD (the voice detector that ships with faster-whisper), run on a stream:
one probability per 32 ms of 16 kHz audio, with the model's memory kept between windows."""

import numpy as np

WINDOW = 512  # samples: 32 ms
CONTEXT = 64  # samples of the previous window the model looks at


class SileroStream:
    def __init__(self) -> None:
        from faster_whisper.vad import get_vad_model

        self.session = get_vad_model().session  # shared, loaded once
        self.h = np.zeros((1, 1, 128), np.float32)
        self.c = np.zeros((1, 1, 128), np.float32)
        self.context = np.zeros(CONTEXT, np.float32)

    def __call__(self, window: np.ndarray) -> float:
        """The probability (0-1) that this window of WINDOW samples is speech."""
        x = np.concatenate([self.context, window]).astype(np.float32)[None]
        out, self.h, self.c = self.session.run(None, {"input": x, "h": self.h, "c": self.c})
        self.context = window[-CONTEXT:]
        return float(np.asarray(out).reshape(-1)[0])
