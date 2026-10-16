"""Benchmark voice chat end to end on this machine: the real /api/voice WebSocket, Whisper,
Piper and the chat model, on a throwaway data folder with two small documents.

    uv run python scripts/voice_bench.py [--runs 3]

Needs Ollama with the chat model, and the voice extra (`uv sync --extra voice`). The question is
spoken by Piper itself, so no microphone is needed. The first run downloads Whisper tiny and the
voice into the throwaway folder. Times are measured from the end of the question (after the
silence that ends it) to: its transcript, the first audio of the answer, and the end of the turn.
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from lumen.voice.tts import Speaker

QUESTIONS = ["Where is the invoice for the garden furniture?", "What do I need for the lentil soup?"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="lumen-voice-bench-"))
    docs = root / "docs"
    docs.mkdir()
    (docs / "invoice-1042.txt").write_text("Invoice 1042 for garden furniture, total 250 EUR, paid 3 May 2025.\n")
    (docs / "lentil-soup.md").write_text("# Lentil soup\nOnion, carrot, red lentils, cumin.\n")
    os.environ.update(
        LUMEN_DATA=str(root / "data"),
        LUMEN_ROOTS=str(docs),
        LUMEN_POWER="saver",
        LUMEN_LOG_DIR=str(root / "logs"),
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from fastapi.testclient import TestClient

    from lumen.api.app import create_app
    from lumen.indexing.pipeline import build_index
    from lumen.voice import tts

    build_index()
    client = TestClient(create_app(), client=("127.0.0.1", 50000))
    t = time.perf_counter()
    speaker = tts.load()  # downloads the voice the first time
    print(f"voice ready in {time.perf_counter() - t:.1f} s")

    rows = []
    for run in range(args.runs):
        for question in QUESTIONS:
            audio = _mic_audio(speaker, question)
            with client.websocket_connect("/api/voice") as ws:
                t = time.perf_counter()
                ready = json.loads(ws.receive_text())
                assert ready["type"] == "ready", ready
                connect = time.perf_counter() - t
                step = 16000 * 2 // 10  # 100 ms chunks
                for i in range(0, len(audio), step):
                    ws.send_bytes(audio[i : i + step])
                end = time.perf_counter()  # the trailing silence has been sent: the question is over
                transcript_at = first_audio_at = None
                said = ""
                while True:
                    message = ws.receive()
                    now = time.perf_counter() - end
                    if message.get("bytes") is not None:
                        first_audio_at = first_audio_at or now
                        continue
                    event = json.loads(message["text"])
                    if event["type"] == "transcript":
                        transcript_at, said = now, event["text"]
                    if event["type"] == "turn_done":
                        rows.append(
                            {
                                "run": run + 1,
                                "question": question,
                                "heard": said,
                                "connect": connect,
                                "transcript": transcript_at,
                                "first_audio": first_audio_at,
                                "done": now,
                            }
                        )
                        break
            r = rows[-1]
            print(
                f"run {r['run']}: heard {r['heard']!r}: transcript {_s(r['transcript'])}, "
                f"first audio {_s(r['first_audio'])}, done {_s(r['done'])} (connect {_s(r['connect'])})"
            )

    warm = [r for r in rows if r["run"] > 1] or rows
    for key in ("transcript", "first_audio", "done"):
        values = [r[key] for r in warm if r[key] is not None]
        if values:
            print(f"median {key}: {_s(statistics.median(values))} (runs after the first)")
    print("plus ~0.7 s of silence before the end of a question is detected")


def _mic_audio(speaker: "Speaker", text: str) -> bytes:
    """The question as microphone audio: Piper's voice resampled to 16 kHz, with room silence
    around it (the trailing second of silence is what ends the question)."""
    pcm = np.frombuffer(b"".join(speaker.speak(text)), np.int16).astype(np.float32)
    rate = speaker.sample_rate
    voice = np.interp(np.arange(0, len(pcm), rate / 16000), np.arange(len(pcm)), pcm)
    quiet = np.random.default_rng(0).normal(0, 100, 16000)
    return np.concatenate([quiet[:8000], voice, quiet]).astype("<i2").tobytes()


def _s(seconds: float | None) -> str:
    return "–" if seconds is None else f"{seconds:.2f} s"


if __name__ == "__main__":
    main()
