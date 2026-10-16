"""The HTTP API for the desktop and phone app (create_app builds it; lumen serve runs it).

Requests from this machine need no token. Phones pair with a 6-digit code shown in the desktop
app and then send `Authorization: Bearer <token>`.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import errors
from .routes import chats, files, images, indexing, pairing, providers, status
from .services import Services


def create_app(lan: bool = False, port: int = 8765) -> FastAPI:
    svc = Services(lan=lan, port=port)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # The indexer runs in its own process group: end it with the server, so nothing keeps
        # running from an app bundle (e.g. an AppImage) after the app is closed.
        svc.indexer.stop()

    app = FastAPI(title="Lumen", lifespan=lifespan)
    app.state.services = svc
    errors.install(app)
    for module in (chats, images, files, status, indexing, providers, pairing):
        app.include_router(module.router)
    return app
