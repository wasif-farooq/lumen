"""`lumen serve`: run the API on this laptop (and, with --lan, for paired phones)."""

from ..core.settings import settings
from .app import create_app
from .network import advertise, lan_ip


def run(lan: bool = False, port: int = 8765):
    import uvicorn

    zc = advertise(port) if lan else None
    where = f"0.0.0.0:{port} (LAN {lan_ip()}:{port})" if lan else f"127.0.0.1:{port}"
    print(f"lumen API on {where} · model {settings.agent_model}", flush=True)
    try:
        uvicorn.run(create_app(lan=lan, port=port), host="0.0.0.0" if lan else "127.0.0.1", port=port,
                    log_level="warning")
    finally:
        if zc:
            zc.close()
