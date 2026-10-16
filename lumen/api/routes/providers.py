"""Model providers, which model does each job, model checks and Ollama downloads."""

import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends

from ...core import errors
from ...core.settings import settings
from ...providers import backends, checks, pulls, registry
from ..deps import auth, local_only, services
from ..responses import Deleted, ModelCheck, ModelOut, ProviderOut, ProvidersOut, ProviderTest, PullOut, Role
from ..schemas import CheckReq, PullReq, RoleReq
from ..services import Services

log = logging.getLogger(__name__)

router = APIRouter()


def _provider_call[T](fn: Callable[..., T], *a: object) -> T:
    try:
        return fn(*a)
    except KeyError as e:
        raise errors.NotFound(e.args[0] if e.args else "Not found") from e
    except ValueError as e:
        raise errors.InvalidInput(str(e)) from e


@router.get("/api/providers", dependencies=[Depends(auth)])
def list_providers() -> ProvidersOut:
    return ProvidersOut(
        providers=[ProviderOut.model_validate(registry.public(p)) for p in settings.providers.values()],
        roles={k: Role.model_validate(v) for k, v in registry.roles().items()},
        speech_models=registry.SPEECH_MODELS,
        pulls=[PullOut.model_validate(p) for p in pulls.pull_status()],
    )


@router.post("/api/providers", dependencies=[Depends(local_only)])
def save_provider(body: dict, svc: Services = Depends(services)) -> ProviderOut:
    p = _provider_call(registry.upsert, body)
    svc.chats.forget_sessions()  # chats pick up a changed address or key
    return ProviderOut.model_validate(registry.public(p))


@router.delete("/api/providers/{pid}", dependencies=[Depends(local_only)])
def delete_provider(pid: str) -> Deleted:
    _provider_call(registry.remove, pid)
    return Deleted(deleted=pid)


@router.get("/api/providers/{pid}/models", dependencies=[Depends(local_only)])
def provider_models(pid: str) -> list[ModelOut]:
    try:
        return [ModelOut.model_validate(x) for x in _provider_call(backends.list_models, pid)]
    except ConnectionError as e:
        raise errors.ProviderUnavailable(str(e) or "Could not connect") from e
    except Exception as e:
        log.warning("listing models of %s failed: %s", pid, e)
        raise errors.ProviderUnavailable(backends.why(e)) from e


@router.post("/api/providers/{pid}/test", dependencies=[Depends(local_only)])
def test_provider(pid: str) -> ProviderTest:
    return ProviderTest.model_validate(_provider_call(backends.test, pid))


@router.post("/api/providers/ollama/pull", dependencies=[Depends(local_only)])
def pull_model(body: PullReq) -> PullOut:
    return PullOut.model_validate(_provider_call(pulls.pull, body.model))


@router.post("/api/models/check", dependencies=[Depends(local_only)])
def check_model(body: CheckReq) -> ModelCheck:
    """Try a model on a job before using it (can take a minute while a local model loads)."""
    return ModelCheck.model_validate(_provider_call(checks.check, body.role, body.provider, body.model))


@router.put("/api/roles", dependencies=[Depends(local_only)])
def set_role(body: RoleReq, svc: Services = Depends(services)) -> dict[str, Role]:
    out = _provider_call(registry.set_role, body.role, body.provider, body.model)
    if body.role == "agent":
        svc.chats.forget_sessions()  # new chats use the new model
    return {k: Role.model_validate(v) for k, v in out.items()}
