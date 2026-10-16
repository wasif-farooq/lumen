"""Who is asking (the laptop itself, a paired phone, or nobody we know), and the app's services."""

from fastapi import Depends, Request

from ..core import errors
from .services import Services


def services(request: Request) -> Services:
    return request.app.state.services


def is_local(request: Request) -> bool:
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost")


def auth(request: Request, svc: Services = Depends(services)) -> str:
    """The laptop itself, or a paired phone (Authorization: Bearer <token>)."""
    if is_local(request):
        return "local"
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    device = svc.pairing.device_for(token)
    if device is None:
        raise errors.NotPaired("Not paired")
    return device


def local_only(request: Request):
    """Settings, keys and pairing: only from the laptop itself."""
    if not is_local(request):
        raise errors.LocalOnly("Only from the laptop itself")


def checked_path(path: str):
    """A path inside the indexed folders that exists; 403 / 404 otherwise."""
    from ..fileops.access import allowed

    try:
        p = allowed(path)
    except PermissionError as e:
        raise errors.OutsideFolders(str(e))
    if not p.exists():
        raise errors.NotFound("File not found")
    return p
