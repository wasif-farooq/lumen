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

## Phase 1: Backend structure ⬜

Move code into small modules by responsibility; behaviour unchanged.

- [ ] `core/`: one `Settings` object (no runtime mutation of module globals), paths, errors
- [ ] `storage/`: connection factory, schema versions, `files_repo`, `chats_repo` (Repository)
- [ ] `indexing/`: pipeline + one class per pass (Pipeline / Strategy); extractors by file type (Strategy); typed progress events replacing the `@@json` strings (Observer)
- [ ] `search/`: text search, query parsing, visual search; add tests for document passages (`find_in_files`, `read_file` with a question) first
- [ ] `providers/`: common interface, Ollama and OpenAI-compatible adapters (Adapter), registry, checks
- [ ] `agent/`: graph, prompts, session, `tools/` split by area
- [ ] `fileops/`: plan / apply / undo (Command)
- [ ] `api/`: `create_app()` factory with a lifespan handler (replaces the deprecated `on_event("shutdown")`), dependencies injected (auth, local-only, db, settings), typed request/response schemas, `routes/` per area, `services/` for long-lived state (indexer, pairing)
- [ ] `cli/`: one file per command
- [ ] No module over ~250 lines; long functions split
- [ ] All Phase 0 tests pass unchanged; packages build and run

## Phase 2: Logging and errors (backend) ⬜

- [ ] Logging setup: logger per module, rotating files in `~/.local/state/lumen/` (`lumen.log`, `indexer.log`), `LUMEN_LOG_LEVEL`
- [ ] Request logging with an id (method, path, status, time)
- [ ] Error types: `NotFound`, `InvalidInput`, `Conflict`, `ProviderUnavailable`, `ModelIncompatible`, `LocalOnly`, each with message + hint
- [ ] One error response shape: `{"error": {"code", "message", "hint", "id"}}` (old `detail` kept during the switch)
- [ ] Unexpected errors: 500 with an id; full traceback in the log under that id
- [ ] Every `except Exception` reviewed: narrowed, or kept on purpose with a logged warning and counted in run stats
- [ ] `print` replaced by logging (CLI keeps its friendly console output)
- [ ] Tests for error responses and logging

## Phase 3: App structure and error display ⬜

- [ ] `core/api/`: `ApiClient` (timeouts, read retries, error parsing → `ApiError`) + one small API class per area
- [ ] `core/models/`: one file per model (Hit, ChatEvent, FileInfo, Provider…)
- [ ] `core/errors/`: `AppError`, `ErrorReporter` (also catches uncaught Flutter/Dart errors)
- [ ] `core/logging/`: console, plus a log file on desktop
- [ ] `features/` (chat, sync, models, settings, pairing, shell): one `ChangeNotifier` controller each; widgets only display
- [ ] `runGuarded` helper replaces the scattered `catch` blocks; switch on lints `avoid_catches_without_on_clauses` (29 today), `discarded_futures` (21), `avoid_dynamic_calls` (79, fixed by typed models)
- [ ] Error display: snackbar + Details (failed action), inline card + Retry (failed load), full screen (server unreachable), dialog (needs a decision), "Something went wrong (id …)" for unexpected ones; never raw exception text
- [ ] Settings → General: "Open logs" and "Copy diagnostics"
- [ ] `shared/widgets/` for reusable pieces; no widget file over ~200 lines
- [ ] All UI tests pass; screenshots unchanged except the new error states

## Phase 4: Clean-up ⬜

- [ ] Remove dead code (including the unused image-hash columns, via a schema version step)
- [ ] Magic numbers → named settings or constants
- [ ] Type hints throughout; docstrings where the "why" isn't obvious; consistent naming
- [ ] No duplicated helpers
- [ ] ruff: CI enforces the full rule set in `pyproject.toml` (114 findings at the start) and `ruff format`
- [ ] Dart: switch on `unawaited_futures`, `prefer_final_locals`, `directives_ordering`, `unnecessary_lambdas`
- [ ] ruff and Dart lints clean with no ignores

## Phase 5: Verify and release ⬜

- [ ] Full test suite, lints, type checks
- [ ] Packages build; smoke test (start, index, chat, close) for the .deb and the AppImage
- [ ] README: architecture section and short contributor guide
- [ ] Pull request reviewed and merged; tag v0.2.0
