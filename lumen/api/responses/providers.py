"""Answers about providers and models."""

from .common import Out


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
