"""Answers about status and settings."""

from .common import Out


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
    voice: bool  # voice chat can run here (its speech engine is installed)


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
    gitignore: bool  # skip what .gitignore files in the indexed folders leave out
    notes_dir: str  # "" = the default
    notes_folder: str  # where notes are saved now
    reminder_notify: bool
    reminder_speak: bool


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
