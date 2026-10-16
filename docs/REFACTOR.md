# Refactor checklist

Goal: a clear structure, proper logging and error handling, errors shown well in the app,
small reusable pieces and clean code, **with no change in behaviour**: same features, same
API paths, same `LUMEN_*` settings, same data folder.

Work happens on the `refactor` branch, one phase at a time; each phase ends green (tests,
lints, package build) and is its own commit. Rules for every code move (from the GitNexus
refactoring guide): `gitnexus_impact` before editing a symbol, `gitnexus_rename` for renames,
`gitnexus_detect_changes` before every commit.

Status: ✅ done · 🔄 in progress · ⬜ not started

---

## Phase 0: Safety net ✅

Tests that pin today's behaviour, so the refactor can be checked against them.

- [x] pytest set up (`tests/`), with a temporary data folder and fake model providers (offline, fast)
- [x] Indexing: scan, text extraction (txt/pdf/docx), changed and deleted files, excluded paths, paused folders
- [x] Pause / resume / stop of an index run, progress events, server shutdown stops the indexer
- [x] Search: words, file type, dates, folder (document passages: not covered yet, see Phase 1)
- [x] Settings: load/save, folder checks, old `OS_OPERATOR_*` names, data folder fallback
- [x] Providers: add/edit/remove, API key never returned, cloud detection, roles, model check (fake)
- [x] File changes: plan → approve → apply → undo; refuses outside indexed folders; never deletes
- [x] HTTP API: one test per route group (status, settings, index, folders, providers, chats, files, pairing), including local-only rules
- [x] ruff configured (target rules in `pyproject.toml`; CI enforces real errors now, the full set from Phase 4); Dart lints stricter (6 rules that pass today)
- [x] CI workflow `checks.yml`: pytest, ruff, flutter analyze, flutter test on every push and PR

Result: 78 tests (`uv run pytest`), stable over repeated runs. Three deliberate breakages
(remote access to settings, changes without approval, date filter ignored) were each caught.
The tests found two real bugs, fixed in their own commit: on first run the server and the
indexer could open the new index at the same moment and fail ("duplicate column name",
"database is locked").

## Phase 1: Backend structure ✅

Move code into small modules by responsibility; behaviour unchanged.

- [x] `core/`: one `Settings` object (no runtime mutation of module globals), preferences, file types, formatting, limits (error types: Phase 2)
- [x] `storage/`: `db` (connection, schema, upgrades), `catalog` and `chats` (Repository) (schema versions: Phase 4, with the unused-column clean-up)
- [x] `indexing/`: pipeline + one class per pass (Pipeline / Strategy); extractors by file type (Strategy); typed progress events replacing the `@@json` strings (Observer)
- [x] Tests for document passages (`find_in_files`, `read_file` with a question), added before moving search
- [x] `search/`: text search, query parsing, visual search
- [x] `providers/`: common interface, Ollama and OpenAI-compatible adapters (Adapter), registry, checks
- [x] `agent/`: graph, prompts, session, `tools/` split by area
- [x] `fileops/`: plan / apply / undo (Command)
- [x] `api/`: `create_app()` factory with a lifespan handler (replaces the deprecated `on_event("shutdown")`), dependencies injected (auth, local-only, db, settings), typed request schemas (response models: Phase 4), `routes/` per area, `services/` for long-lived state (indexer, pairing)
- [x] `cli/`: one file per command
- [x] No module over ~250 lines; long functions split
- [x] All behaviour checks still pass (tests now reach internals only through conftest fixtures); package build checked in Phase 5

Result: `lumen/` is now `core/`, `storage/`, `indexing/`, `search/`, `providers/`, `agent/`,
`fileops/`, `api/` and `cli/`; the largest module is 256 lines (`server.py` was 947). The API's
state (index runner, chats, pairing) lives in a `Services` object per app instead of module
globals, and every test gets its own app. 110 tests, including one that resolves every relative
import (also inside functions).

Behaviour changes, each with a test: pausing a re-scan where nothing changed now holds (it was
ignored); `lumen index --power` stays an override for that run. Found on the way: the package
build's import check still named the old `lumen.server` (fixed).

## Phase 2: Logging and errors (backend) ✅

- [x] Logging setup (`core/logging.py`): logger per module, rotating files in `~/.local/state/lumen/` (`lumen.log`, `indexer.log`, `cli.log`), `LUMEN_LOG_LEVEL`, `LUMEN_LOG_DIR`
- [x] Request logging with an id (method, path, status, time); the id is in every log line and in `X-Request-ID`
- [x] Error types (`core/errors.py`): `InvalidInput`, `NotPaired`, `LocalOnly`, `OutsideFolders`, `WrongCode`, `NotFound`, `Conflict`, `ProviderUnavailable`, each with message + hint (`ModelIncompatible` dropped: a failed model check is a result the app shows, not an error)
- [x] One error response shape: `{"detail", "error": {"code", "message", "hint", "id"}}`, also for FastAPI's own 404/405/422 (`detail` kept for older apps)
- [x] Unexpected errors: 500 with an id; full traceback in the log under that id, never in the answer
- [x] Every `except Exception` reviewed: all sit where a library can raise anything (PyMuPDF, PIL, Ollama, OpenAI, whisper); each now logs what it swallowed, and per-file failures were already counted in run stats
- [x] `print` replaced by logging in `serve` (the CLI keeps its console output; the indexer's `@@` progress lines are its protocol)
- [x] An index run that crashes shows an error in the app (`error` in `/api/index`) instead of just ending
- [x] `/api/diagnostics` (laptop only, no keys) for the app's "Copy diagnostics"
- [x] Tests for error responses and logging (`test_errors_and_logs.py`, 13 tests)

## Phase 3: App structure and error display ✅

- [x] `core/api/`: `ApiClient` (timeouts, one retry for reads nobody answered, error parsing → `ApiError` with code, message, hint and request id) + one small API mixin per area (system, chats, files, index, providers, pairing)
- [x] `core/models/`: `Hit`, `Chat`/`ChatEvent`, `FileInfo`/`Segment`, and `json.dart` helpers for reading nested JSON safely
- [x] `core/errors/`: `userMessage`, `ErrorReporter` (uncaught Flutter and async errors go to the log, one calm line on screen), `runGuarded`
- [x] `core/logging/`: console in debug, the last 300 lines in memory, `app.log` on desktop next to the server's logs; repeated lines are folded
- [x] `features/` (chat, preview, sync, models, settings, pairing, shell): a `ChangeNotifier` controller each for sync, models and general settings (chat state stays in `AppState`, split into `ChatState`); dialogs and messages in `*_actions.dart`; widgets only display
- [x] `runGuarded` replaces the scattered `catch` blocks; lints on: `avoid_catches_without_on_clauses`, `discarded_futures`, `unawaited_futures`, `avoid_dynamic_calls` (60 findings after the split, all fixed)
- [x] Error display: snackbar + Details (failed action: hint and request id), inline card + Retry (failed load), full screen (server unreachable, desktop), dialog (a folder that could not be added); "Something went wrong (id …)" for unexpected server errors; never raw exception text
- [x] An index run that crashed shows "Indexing stopped unexpectedly" with where the log is
- [x] Settings → General: "Problems" card with "Open logs" and "Copy diagnostics" (server versions, models, last log lines and the app log; no keys)
- [x] `shared/widgets/` for reusable pieces; no file over 200 lines (largest: `chat_view.dart`, 184)
- [x] Golden screenshots unchanged except Settings (the new Problems card); 7 new tests for error display (23 in all)

## Phase 4: Clean-up ✅

- [x] Remove dead code: the unused image-hash columns (`dhash`, `sha1`) dropped by the first schema version step (`PRAGMA user_version`); the unused Langfuse fields of `/api/status`; vulture finds nothing else
- [x] API response models (`api/responses.py`, typed answer for each route; the JSON of every GET is identical to before, checked against the old server)
- [x] Magic numbers → named constants where they are tunables (port, agent read budgets, thumbnail/upload sizes, timeouts, image-search thresholds, log sizes); unit conversions and image-model sizes stay inline
- [x] Type hints throughout (ruff `ANN` enforced in `lumen/`), pyright (basic) in CI with 0 errors; docstrings where the "why" isn't obvious
- [x] No duplicated helpers: one private-file writer for API keys and paired devices (`core/private_files.py`; it also closes a moment where `devices.json` was readable by others)
- [x] ruff: CI enforces the full rule set (`E, W, F, I, B, UP, SIM, ANN`; 69 findings fixed) and `ruff format`
- [x] Dart: `unawaited_futures`, `prefer_final_locals`, `directives_ordering`, `unnecessary_lambdas` on
- [x] ruff, pyright and Dart lints clean with no ignores in the code (only rule-level choices in `pyproject.toml`: `B008` for FastAPI's `Depends`, `ANN401`, and no `ANN` for tests)

## Phase 5: Verify and release ✅

- [x] Full test suite, lints, type checks: 130 server tests, 23 app tests, ruff (full rule set + format), pyright, flutter analyze; all green in CI
- [x] Packages build (from a clean checkout, in Docker): `lumen_0.2.0-rc1_amd64.deb` (171 MB) and `Lumen-0.2.0-rc1-x86_64.AppImage` (226 MB). Smoke test of the packaged server: starts in 0.5 s, indexes, searches, answers a chat with the local model (qwen3.5:2b, 17 s, using its search tool), returns the new error shape, shuts down on SIGTERM, writes its logs. The app binary's libraries all resolve; the window itself was not opened (no display in the build container)
- [x] README: install, logs and troubleshooting, architecture, contributor guide
- [x] Pull request reviewed and merged; tagged v0.2.0

## Results

| | Before | After |
|---|---|---|
| Largest Python module | `server.py`, 947 lines | 195 lines |
| Largest Dart file | `models_screen.dart`, 888 lines | 184 lines |
| Server tests | 78 | 130 |
| App tests | 16 | 23 |
| Lint (server) | F, E9 only | E, W, F, I, B, UP, SIM, ANN + ruff format + pyright |
| Lint (app) | recommended + 6 rules | + 7 more (error handling and style), all clean |
| Errors in the app | raw exception text | the server's message, Details with hint and request id, Retry |
| Logs | none (prints) | rotating files per part, request ids, "Copy diagnostics" |
