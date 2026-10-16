"""One error shape for every failed request, and a request id that ties it to the log.

    {"detail": "<message>", "error": {"code", "message", "hint", "id"}}

Unexpected errors answer 500 with only the id (the traceback goes to the log, not to the app).
"""

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core import errors
from ..core.logging import request_id

log = logging.getLogger("lumen.api")


def body(code: str, message: str, hint: str = "", rid: str = "", detail=None) -> dict:
    return {"detail": message if detail is None else detail,
            "error": {"code": code, "message": message, "hint": hint, "id": rid}}


def _rid(request: Request) -> str:
    return request.scope.get("lumen.request_id", "")


def install(app: FastAPI):
    @app.exception_handler(errors.LumenError)
    async def lumen_error(request: Request, e: errors.LumenError):
        log.info("%s %s -> %s %s: %s", request.method, request.url.path, e.status, e.code, e.message)
        return JSONResponse(body(e.code, e.message, e.hint, _rid(request)), status_code=e.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException):
        message = e.detail if isinstance(e.detail, str) else json.dumps(e.detail)
        return JSONResponse(body(errors.CODES.get(e.status_code, "error"), message, rid=_rid(request)),
                            status_code=e.status_code, headers=getattr(e, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, e: RequestValidationError):
        problems = e.errors()
        first = problems[0] if problems else {}
        where = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
        message = f"{where}: {first.get('msg', 'invalid')}" if where else first.get("msg", "Invalid request")
        # detail stays FastAPI's list, as before
        return JSONResponse(body("invalid_input", message, rid=_rid(request), detail=e.errors()), status_code=422)

    app.add_middleware(RequestIds)


class RequestIds:
    """Give each request an id (X-Request-ID), log it, and turn crashes into a JSON 500.
    Plain ASGI rather than BaseHTTPMiddleware, so streamed chat answers pass straight through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = uuid.uuid4().hex[:8]
        scope["lumen.request_id"] = rid
        token = request_id.set(rid)
        started, status = time.monotonic(), {"code": 0}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("%s %s failed", scope.get("method"), scope.get("path"))
            if status["code"]:  # the answer had already started (a stream): nothing more to send
                return
            status["code"] = 500
            response = JSONResponse(
                body("internal", f"Something went wrong (id {rid}). The details are in the log.", rid=rid),
                status_code=500, headers={"x-request-id": rid})
            await response(scope, receive, send)
        finally:
            ms = (time.monotonic() - started) * 1000
            level = logging.WARNING if status["code"] >= 500 else logging.DEBUG
            log.log(level, "%s %s %s %.0fms", scope.get("method"), scope.get("path"), status["code"], ms)
            request_id.reset(token)
