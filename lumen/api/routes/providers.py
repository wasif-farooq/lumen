"""Model providers, which model does each job, model checks and Ollama downloads."""

from fastapi import APIRouter, Depends, HTTPException

from ...core.settings import settings
from ...providers import backends, checks, pulls, registry
from ..deps import auth, local_only, services
from ..schemas import CheckReq, PullReq, RoleReq
from ..services import Services

router = APIRouter()


def _provider_call(fn, *a):
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, e.args[0] if e.args else "Not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/providers", dependencies=[Depends(auth)])
def list_providers():
    return {"providers": [registry.public(p) for p in settings.providers.values()], "roles": registry.roles(),
            "speech_models": registry.SPEECH_MODELS, "pulls": pulls.pull_status()}


@router.post("/api/providers", dependencies=[Depends(local_only)])
def save_provider(body: dict, svc: Services = Depends(services)):
    p = _provider_call(registry.upsert, body)
    svc.chats.forget_sessions()  # chats pick up a changed address or key
    return registry.public(p)


@router.delete("/api/providers/{pid}", dependencies=[Depends(local_only)])
def delete_provider(pid: str):
    _provider_call(registry.remove, pid)
    return {"deleted": pid}


@router.get("/api/providers/{pid}/models", dependencies=[Depends(local_only)])
def provider_models(pid: str):
    try:
        return _provider_call(backends.list_models, pid)
    except ConnectionError as e:
        raise HTTPException(502, str(e) or "Could not connect")
    except Exception as e:
        raise HTTPException(502, backends.why(e))


@router.post("/api/providers/{pid}/test", dependencies=[Depends(local_only)])
def test_provider(pid: str):
    return _provider_call(backends.test, pid)


@router.post("/api/providers/ollama/pull", dependencies=[Depends(local_only)])
def pull_model(body: PullReq):
    return _provider_call(pulls.pull, body.model)


@router.post("/api/models/check", dependencies=[Depends(local_only)])
def check_model(body: CheckReq):
    """Try a model on a job before using it (can take a minute while a local model loads)."""
    return _provider_call(checks.check, body.role, body.provider, body.model)


@router.put("/api/roles", dependencies=[Depends(local_only)])
def set_role(body: RoleReq, svc: Services = Depends(services)):
    out = _provider_call(registry.set_role, body.role, body.provider, body.model)
    if body.role == "agent":
        svc.chats.forget_sessions()  # new chats use the new model
    return out
