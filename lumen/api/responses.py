"""What the API answers, route by route (FastAPI documents and checks these).

Each model names the fields the app relies on, with their types. Extra fields are allowed and
passed on as they are, so adding one in the code never silently drops it from an answer.
"""

from pydantic import BaseModel, ConfigDict


class Out(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------- small answers ----------


class Ok(Out):
    ok: bool = True


class Message(Out):
    ok: bool = True
    message: str


class Deleted(Out):
    deleted: str


# ---------- files and search ----------


class HitOut(Out):
    """A file found by a search."""

    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    snippet: str = ""
    duration: float | None = None
    at: float | None = None  # where in a video/audio the words are said (seconds)
    at_text: str = ""
    partial: bool = False


class ImageHitOut(HitOut):
    score: float  # how well it matched (higher is better)


class SegmentOut(Out):
    start: float
    end: float
    text: str
    time: str


class FileInfoOut(Out):
    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    folder: str
    indexed: bool
    searchable: bool
    caption: str
    duration: float | None
    excerpt: str
    segments: list[SegmentOut]


# ---------- chats ----------


class ChatOut(Out):
    id: str
    title: str
    created: float
    updated: float


class ChatEventOut(Out):
    """One thing in a conversation (user, tool_call, results, answer, approval…); its other
    fields depend on the type."""

    type: str
    at: float | None = None


class Pending(Out):
    pending: dict | None


# ---------- index runs ----------


class IndexStarted(Out):
    running: bool


class IndexStopped(Out):
    stopped: bool
    running: bool


class IndexPausing(Out):
    pausing: bool
    running: bool


class RecentFile(Out):
    phase: str | None
    path: str
    note: str | None
    ext: str | None
    kind: str | None


class IndexProgressOut(Out):
    running: bool
    started: float | None
    phase: str | None
    done: int
    total: int
    path: str | None
    note: str | None
    scanned: int
    ext: str | None
    kind: str | None
    paused: bool
    pausing: bool
    summary: dict | None
    error: str | None  # set when the indexer process ended with an error
    eta: int | None  # seconds left in this step
    recent: list[RecentFile]
    lines: list[str]


class Excluded(Out):
    excluded: list[str]


class ExcludedAndRemoved(Excluded):
    removed: int


class Removed(Out):
    removed: int


class FolderPaused(Out):
    paused: bool


# ---------- status and settings ----------


class IndexStats(Out):
    files: int
    with_text: int
    captioned: int
    media_indexed: int
    transcript_lines: int
    visual_indexed: int


class FolderOut(Out):
    path: str
    files: int
    paused: bool


class PowerOut(Out):
    on_ac: bool
    battery: int | None
    mode: str
    ai_allowed: bool
    reason: str
    threads: int


class ModelsOut(Out):
    agent: str
    vision: str
    speech: str
    agent_provider: str
    vision_provider: str
    agent_cloud: bool
    vision_cloud: bool
    cpu_only: bool
    ollama_ok: bool
    loaded: list[str]


class StatusOut(Out):
    host: str
    index: IndexStats
    last_index: dict | None
    indexing: bool
    index_paused: bool
    folders: list[FolderOut]
    power: PowerOut
    models: ModelsOut
    lan: bool
    open_mode: str


class SettingsOut(Out):
    roots: list[str]
    paused_roots: list[str]
    excluded: list[str]
    power_mode: str
    threads: int
    cpu_only: bool
    captions: bool
    media: bool
    transcripts: bool
    visual: bool


class Diagnostics(Out):
    version: str
    python: str
    platform: str
    roles: dict
    power_mode: str
    cpu_only: bool
    folders: int
    indexing: bool
    log_dir: str
    logs: dict[str, list[str]]


# ---------- providers and models ----------


class ProviderOut(Out):
    """A provider as the app sees it: never the API key itself."""

    id: str
    name: str
    kind: str
    base_url: str
    has_key: bool
    key_hint: str
    cloud: bool
    builtin: bool
    used_by: list[str]


class Role(Out):
    provider: str
    model: str


class PullOut(Out):
    model: str
    status: str
    completed: int
    total: int
    done: bool
    error: str | None = None


class ProvidersOut(Out):
    providers: list[ProviderOut]
    roles: dict[str, Role]
    speech_models: list[str]
    pulls: list[PullOut]


class ModelOut(Out):
    id: str
    size: int | None
    vision: bool | None
    tools: bool | None


class ProviderTest(Out):
    ok: bool
    message: str


class CheckStep(Out):
    name: str
    ok: bool
    detail: str


class ModelCheck(Out):
    ok: bool
    checks: list[CheckStep]
    seconds: float


# ---------- pairing ----------


class PairStarted(Out):
    code: str
    expires_in: int
    lan: bool
    address: str


class Paired(Out):
    token: str
    host: str
    device_id: str


class DeviceOut(Out):
    id: str
    name: str
    paired: float


class Hello(Out):
    app: str
    host: str
