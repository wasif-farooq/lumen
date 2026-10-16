"""`lumen serve`: run the API on this laptop (and, with --lan, for paired phones)."""

import logging

from ..core import logging as lumen_logging
from ..core.limits import DEFAULT_PORT
from ..core.settings import settings
from .app import create_app
from .network import advertise, lan_ip

log = logging.getLogger("lumen.serve")


def run(lan: bool = False, port: int = DEFAULT_PORT) -> None:
    import uvicorn

    path = lumen_logging.setup("server", console=True)
    zc = advertise(port) if lan else None
    where = f"0.0.0.0:{port} (LAN {lan_ip()}:{port})" if lan else f"127.0.0.1:{port}"
    log.info("lumen API on %s · model %s · log %s", where, settings.agent_model, path)
    try:
        uvicorn.run(
            create_app(lan=lan, port=port), host="0.0.0.0" if lan else "127.0.0.1", port=port, log_level="warning"
        )
    finally:
        if zc:
            zc.close()
