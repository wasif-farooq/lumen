"""Who is asking (the laptop itself, a paired phone, or nobody we know), and the app's services."""

from pathlib import Path

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from ..core import errors
from .services import Services


def services(request: Request) -> Services:
    return request.app.state.services


def is_local(conn: HTTPConnection) -> bool:
    return conn.client is not None and conn.client.host in ("127.0.0.1", "::1", "localhost")


def who(conn: HTTPConnection, svc: Services) -> str:
    """The laptop itself ("local"), or the id of a paired phone; raises NotPaired otherwise.
    Phones send `Authorization: Bearer <token>`; a WebSocket that can't set headers may use
    `?token=` instead."""
    if is_local(conn):
        return "local"
    token = conn.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token and conn.scope["type"] == "websocket":
        token = conn.query_params.get("token", "")
    device = svc.pairing.device_for(token)
    if device is None:
        raise errors.NotPaired("Not paired")
    return device


def auth(request: Request, svc: Services = Depends(services)) -> str:
    """The laptop itself, or a paired phone (Authorization: Bearer <token>)."""
    return who(request, svc)


def local_only(request: Request) -> None:
    """Settings, keys and pairing: only from the laptop itself."""
    if not is_local(request):
        raise errors.LocalOnly("Only from the laptop itself")


def checked_path(path: str) -> Path:
    """A path inside the indexed folders that exists; 403 / 404 otherwise."""
    from ..fileops.access import allowed

    try:
        p = allowed(path)
    except PermissionError as e:
        raise errors.OutsideFolders(str(e)) from e
    if not p.exists():
        raise errors.NotFound("File not found")
    return p
