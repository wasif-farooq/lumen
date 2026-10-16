# Lumen

A local AI assistant for your files. Ask in your own words, "find my CV", "photos of the beach", "the video where someone asks when the last train leaves", and Lumen finds it: by name, by the text inside documents, by what images and videos show, and by what is said in them.

It runs on your laptop with a local model (Ollama) by default. Nothing leaves the machine unless you point it at a cloud provider yourself.

![Chat with search results and a file preview](app/test/screens/desktop_chat.png)

## What it does

- **Searches everything you index**: file names, the text of PDFs, Word, Excel and PowerPoint files, OpenDocument files, e-books (EPUB), notes and code, descriptions of photos and scanned pages, and transcripts of video and audio with timestamps ("play it at 10:05").
- **Finds pictures by what they show**, and finds images that look like a given photo (drop one on the chat).
- **Answers questions about a file** by reading it, and opens files or shows them in their folder.
- **Organises files with your approval**: create folders and files, copy, move and rename. Every change asks first and can be undone. It cannot delete anything.
- **Skips what code projects ignore**: build output, caches and logs listed in their `.gitignore` files (a switch in Settings → Sync).
- **Indexes quietly**: low CPU and disk priority, and in Auto mode the AI work only runs while plugged in. Pause, resume or stop a run any time, and see live progress.
- **Desktop and phone app** (Flutter): the Linux desktop app, plus a phone app that pairs with your laptop over the local network.

## How it works

```
Flutter app (desktop / phone)
        │  HTTP
        ▼
lumen serve ── chat agent (LangGraph + tools) ── model provider (Ollama or OpenAI-compatible)
        │
        └── lumen index (separate low-priority process)
              files → text (PDF, Word, Excel, PowerPoint, OpenDocument, EPUB, text/code),
                      read in pieces: long PDFs and big files to the end (up to 10M characters each)
              images & scans → descriptions (vision model)
              video & audio → frame descriptions + speech transcripts (faster-whisper, CPU)
              images → visual signatures for search and look-alikes (CLIP, CPU)
              everything → SQLite full-text index
```

Data lives in one folder (`~/.local/share/lumen` by default): the index, chats, settings and provider keys.

## Install

Download the `.deb` or the AppImage from [Releases](https://github.com/wasif-farooq/lumen/releases). Both hold the app and the server; you only need [Ollama](https://ollama.com) (or another model provider) and `ffmpeg`.

```bash
sudo apt install ./lumen_*_amd64.deb      # then start "Lumen" from the menu, or: lumen-app
```

## Quick start (from source)

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com) and `ffmpeg`.

```bash
git clone https://github.com/wasif-farooq/lumen.git
cd lumen
uv sync

ollama pull qwen3.5:2b        # chat and image descriptions (small, fast)

uv run lumen index            # index ~/Documents, ~/Downloads and ~/Desktop
uv run lumen chat             # chat in the terminal
```

Other commands:

```bash
uv run lumen ask "what files do I have about tax?"
uv run lumen search invoice --ext pdf --after 2025-01-01
uv run lumen stats
uv run lumen serve            # API for the app on 127.0.0.1:8765 (add --lan for phones)
```

## The app

Start the API with `uv run lumen serve`, then run the app:

```bash
cd app
flutter run -d linux
```

To build the Linux app without installing a toolchain on your machine, build it in Docker:

```bash
docker compose --profile build run --rm app-build   # → app/dist/linux/lumen
```

More in [app/README.md](app/README.md), including the phone app and pairing.

| Settings: models and providers | Sync: live indexing progress |
|---|---|
| ![Models](app/test/screens/desktop_models.png) | ![Sync](app/test/screens/desktop_index_running.png) |

## Models and providers

In **Settings → Models** you choose which model does each job:

- **Chat agent**: needs tool calling.
- **Images & video**: needs vision.
- **Speech**: a local whisper size, always on the CPU.

Models can come from Ollama (the app lists what you have and can download more) or any **OpenAI-compatible** server: LM Studio, llama.cpp, vLLM, OpenAI, OpenRouter. A new model is tried on its job before it is used: the chat model must call a tool, the vision model must read a test picture.

Providers outside your laptop and local network are marked **Cloud**, and Lumen asks before sending anything to one. API keys are stored only in your data folder, readable by your user account, and are never sent back to the app.

## Configuration

Most settings live in the app (Settings → General / Models / Sync). Environment variables set the defaults:

| Variable | Default | |
|---|---|---|
| `LUMEN_ROOTS` | `~/Documents:~/Downloads:~/Desktop` | Folders to index |
| `LUMEN_DATA` | `~/.local/share/lumen` | Where the index, chats and settings live |
| `LUMEN_MODEL` | `qwen3.5:2b` | Chat model on Ollama |
| `LUMEN_CAPTION_MODEL` | same as `LUMEN_MODEL` | Model that describes images and video |
| `LUMEN_WHISPER_MODEL` | `small` | Speech-to-text size |
| `LUMEN_POWER` | `auto` | `auto` (AI work only when plugged in), `saver` (no models), `performance` |
| `LUMEN_CPU_ONLY` | `0` | `1` keeps every model on the CPU |
| `LUMEN_THREADS` | `4` | CPU threads for indexing |
| `LUMEN_CAPTIONS`, `LUMEN_MEDIA`, `LUMEN_TRANSCRIPTS`, `LUMEN_VISUAL` | `1` | Turn indexing passes off with `0` |
| `LUMEN_GITIGNORE` | `1` | `0` also indexes what `.gitignore` files in code projects leave out |
| `LUMEN_WRITE` | `1` | `0` reports file changes instead of doing them |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `LUMEN_LOG_LEVEL` | `INFO` | `DEBUG` for more detail in the logs |
| `LUMEN_LOG_DIR` | `~/.local/state/lumen` | Where the logs go |

Copy `.env.example` to `.env` for local overrides (it is git-ignored). Optional [Langfuse](https://langfuse.com) tracing is turned on by its `LANGFUSE_*` keys.

## When something goes wrong

The app says what failed in plain words. When the server gave more, **Details** shows what to try and a request id. The same id is on the matching lines of the server's log, so a problem can be traced from the message to its cause.

Logs are in `~/.local/state/lumen/`:

| File | What writes it |
|---|---|
| `lumen.log` | the server: every request (with its id), chats, model calls, errors with tracebacks |
| `indexer.log` | index runs |
| `app.log` | the desktop app |
| `cli.log` | terminal commands (`lumen ask`, `search`, …) |
| `server.log` | the packaged app's server output (also catches a server that fails to start) |

**Settings → General → Problems** opens this folder and copies a summary for a bug report: versions, which model does what, and the last log lines. It never contains API keys.

## Run in the background

`deploy/` has systemd user units: `lumen-api.service` keeps the API running, and `lumen-index.service` with `lumen-index.timer` re-indexes every 30 minutes at idle priority. Install instructions are at the top of `lumen-api.service` and `lumen-index.service`; first change `WorkingDirectory` and `LUMEN_DATA` in them to where you cloned Lumen.

## Try it safely in Docker

The Docker setup mounts your folders **read-only**, and opening files only reports what would be opened:

```bash
docker compose run --rm app index
docker compose run -d --rm --name lumen-api app serve
```

## Architecture

The server (`lumen/`) is a package per area. Each one exposes a few functions or classes; the rest is internal.

| Package | What it does | Patterns |
|---|---|---|
| `core/` | settings (one `Settings` object), saved preferences, typed errors, logging, file types, limits | |
| `storage/` | the SQLite index (schema, upgrades via `PRAGMA user_version`), the file catalog, chat history | Repository |
| `indexing/` | an index run: scan, then the AI passes (captions, visual signatures, video/audio), then passages; progress events; power and pause | Pipeline, Strategy (passes, text extractors), Observer (progress) |
| `search/` | full-text search, passages for questions, visual search, hybrid image search | |
| `providers/` | Ollama and OpenAI-compatible backends behind one interface, the provider registry, model checks, Ollama downloads | Adapter |
| `agent/` | the LangGraph agent, its prompts, a chat session, and its tools by area | |
| `fileops/` | file changes: plan, approve, apply, undo (journal) | Command |
| `api/` | `create_app()`: routes per area, request and response models, services per app (indexer, chats, pairing), auth, one error shape | Factory, dependency injection |
| `cli/` | one module per `lumen` command | |

Errors are raised as `core.errors` types (`NotFound`, `InvalidInput`, `Conflict`, …) with a message for people and an optional hint. The API turns them into `{"detail", "error": {code, message, hint, id}}`; anything unexpected becomes a 500 with only an id, and the traceback goes to the log.

The app (`app/lib/`) has the same shape:

- `core/`: `api/` (an `ApiClient` with timeouts and error parsing, one mixin per area), `models/`, `errors/` (`runGuarded`, the reporter for uncaught errors), `logging/`, and `AppState` (the connection to one laptop, with the chats).
- `features/`: chat, preview, sync, models, settings, pairing and the desktop/phone shells. Each has a `ChangeNotifier` controller, an `*_actions.dart` for dialogs and messages, and widgets that only display.
- `shared/`: the theme and reusable widgets, including the error views (snackbar with Details, a card with Retry).

## Contributing

```bash
uv sync                                       # Python, with the dev tools
uv run pytest                                 # the server's tests (fast, offline, no models)
uv run ruff check lumen tests scripts         # lint (the full rule set)
uv run ruff format lumen tests scripts        # format
uv run pyright                                # types

cd app
flutter analyze && flutter test               # the app (or in Docker, see docker/)
flutter test --update-goldens                 # after an intended UI change: refresh app/test/screens
```

CI runs all of these on every pull request.

**Releases are automatic.** Every push to `main` that passes CI is tagged with the next version and its `.deb` and AppImage are published. The version goes up a patch (0.2.0 → 0.2.1); put `[minor]` or `[major]` in a commit message to go up further, or `[skip release]` to hold back. Pushes that only change documentation or CI make no release. The rules are in `.github/scripts/next-version.sh`, which you can run locally to see what the next release would be.

- **Tests describe behaviour through the HTTP API** (and the CLI), the way the app uses Lumen. Only `tests/conftest.py` knows the internal module layout, so code can move without rewriting tests.
- **Every change of behaviour comes with a test**, and a bug fix with the test that would have caught it.
- **Raise `core.errors` types** for anything the user should read; never return raw exception text to the app. In the app, run user actions through `runGuarded`.
- **Keep modules small**: one job per module, about 250 lines at most in Python and 200 in Dart.
- **Privacy**: the UI fixtures in `app/test/fixtures` are made-up demo data. Don't record new fixtures from your own files without removing personal details first.

## License

[MIT](LICENSE)
