"""This laptop on the local network: its address, and announcing the server so phones find it."""

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zeroconf import Zeroconf


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def advertise(port: int) -> "Zeroconf":
    """Announce the server on the LAN (mDNS) so the phone app can find it. Close the result to stop."""
    from zeroconf import ServiceInfo, Zeroconf

    host = socket.gethostname()
    info = ServiceInfo(
        "_lumen._tcp.local.",
        f"{host}._lumen._tcp.local.",
        addresses=[socket.inet_aton(lan_ip())],
        port=port,
        properties={"host": host},
        server=f"{host}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    return zc
