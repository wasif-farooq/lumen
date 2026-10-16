# Real-time voice chat: plan and checklist

Talk to Lumen and hear the answer: speech in (Whisper tiny), the same chat agent as typed chat
(search, read, open, changes with approval), speech out (Piper). Voice turns are part of the chat
history, so a conversation can switch between typing and talking.

Measured on the development laptop (RTX 3050, 4 GB; numbers from a standalone benchmark):

| Stage | Time |
|---|---|
| Whisper tiny, 3 s question (CPU int8) | 0.23 s |
| qwen3.5:2b first sentence, warm (GPU) | 0.42 s |
| Agent turn with a search, warm | 1.3–5 s |
| Piper, first audio of a sentence (CPU) | 0.12 s |
| Model cold start | 12.4 s (so voice keeps the model loaded) |

Target: speech starts within about 1.5 s of the end of a plain question, and the agent says it is
looking when a search will take longer.

## Design

```
app (mic, speaker)  ── WebSocket /api/voice ──  lumen serve
  PCM16 16 kHz  ───────────────────────────▶  Endpointer: speech start / end of utterance
                                               Whisper tiny (CPU, kept loaded) → transcript
                                               chat agent (same session and history as typed chat)
                                               answer → speakable sentences (no markdown, file names
                                                         instead of paths)
  ◀───────────────────────────  PCM16 22.05 kHz  Piper, one sentence at a time
  ◀── JSON events: transcript, tool_call, results, approval, answer, speaking, turn_done, error
```

- **Protocol** (`/api/voice?chat_id=…`): binary frames are audio (client: PCM16 mono 16 kHz;
  server: PCM16 mono at the voice's rate, announced in `ready`). Text frames are JSON events.
  Client → server: `stop` (end the utterance now, for push-to-talk), `interrupt` (stop speaking),
  `approve` (answer a pending change). Same auth as the REST API: the laptop needs nothing, phones
  send their token (header, or `?token=` where a WebSocket can't set headers).
- **Endpointing**: Silero VAD (shipped inside faster-whisper, MIT) scores every 32 ms; speech
  starts after 64 ms above 0.5, the utterance ends after ~0.7 s below 0.35, and is cut at 30 s.
  A loudness-based detector was tried first and failed on real audio: digital silence (a muted or
  warming-up microphone, or a phone's noise suppression between words) dragged its estimate of
  the room down until ordinary noise looked like speech, and a question never ended.
- **Models stay loaded** while a voice connection is open: Whisper and Piper in the server
  process, the chat model in Ollama (warmed with the agent's own options, so it is not reloaded).
- **One model at a time**: voice and typed chat share the chat lock, as typed chats do today.
- **Barge-in**: `interrupt` stops the audio still queued. The server does not listen while it
  answers: without echo cancellation its own voice from the speakers would start a new turn.
- **Searches**: when the agent starts searching, it says "One moment." so the wait isn't silent.
- **Speech out is a backend** (`voice/tts.py`), so Piper can be swapped for another engine.

## Licensing (decision needed before packaging)

Piper (`piper-tts`, piper1-gpl) is **GPL-3.0**; Lumen is MIT and its packages bundle their
dependencies. Until decided, Piper is an optional extra (`uv sync --extra voice`) and is not in
the .deb / AppImage. Options: bundle it (the packages become GPL as a whole), keep it a separate
download, or use a permissively licensed TTS engine. Whisper (faster-whisper) and Silero VAD are
MIT. Each Piper voice has its own licence (see its MODEL_CARD); check the chosen voice's before
shipping it by default.

## Phase 1: Server ✅

- [x] `lumen/voice/`: endpointer (Silero VAD, streamed), speech-to-text (Whisper tiny, kept
      loaded), text-to-speech backend (Piper; the voice is downloaded on first use into the data
      folder, after checking the engine is installed), speakable sentences
- [x] Settings: `voice_stt_model` (tiny), `voice_tts_voice` (en_US-lessac-medium)
- [x] `/api/voice` WebSocket: auth (header, or `?token=`), `ready`, turn loop (audio → transcript →
      agent → speech), events recorded in the chat history, `stop`, `interrupt`, approvals by
      voice ("yes" / "no") or by button. Typed and spoken chat share one turn (`Chats.turn`).
- [x] Keep the chat model warm for the length of a voice connection (Ollama)
- [x] Clear errors: voice extra not installed (nothing downloaded), voice download failed, no
      speech heard
- [x] Tests with fake speech models (12): a full turn, push-to-talk, noise, interrupting, a spoken
      yes and no, the approval button, its own voice not taken as a question, continuing a chat,
      auth, the missing extra, and the real voice detector on noise and digital silence. Each of
      interrupting, not listening while answering, and a spoken "no" was checked by breaking it.
- [x] Benchmark script for the real pipeline (`scripts/voice_bench.py`)

Measured with the real pipeline (`scripts/voice_bench.py --runs 3`, warm, medians), from the end
of the question: transcript 0.66 s; first audio 1.75 s ("One moment." while it searches); whole
answer 4.8 s (2.2 s for a one-search answer, 6–7 s when the agent reads a file too). Add ~0.7 s
of silence that ends a question. The first question of a session waited 11 s for the chat model
to load: Phase 2 should open the voice connection before the user speaks.

## Phase 2: App

- [ ] Microphone capture (PCM16 16 kHz) and streamed playback on Linux desktop and Android;
      pick the packages with a small spike in the Docker build first
- [ ] Voice button in the composer; states: listening, thinking, speaking; tap to interrupt
- [ ] Open the voice connection when voice mode is turned on (so the chat model is loaded before
      the first question)
- [ ] Hands-free (voice detection) and push-to-talk modes
- [ ] Voice turns shown in the chat like typed ones (transcript as the user bubble)
- [ ] Errors: no microphone or permission, server without voice support, connection lost
- [ ] Settings → General: voice on/off, speech model size, voice

## Phase 3: Ship

- [ ] Licensing decision (above), then packaging: voice extra in the bundle or a separate download
- [ ] First-use download of the voice with progress in the app
- [ ] README: voice chat, privacy (audio never leaves the laptop with local models)
- [ ] Real-device test on a phone; latency check against the target
