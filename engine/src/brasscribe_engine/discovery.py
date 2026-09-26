"""DNS-SD (Bonjour/mDNS) advertisement so Play apps on the LAN can find the engine.

The advertisement only says where the engine is; clients still pair with the printed code.
"""

from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager
from typing import Iterator

from . import __version__

SERVICE_TYPE = "_brasscribe._tcp.local."


def lan_only(addresses: list[str]) -> list[str]:
    """Drop 100.64.0.0/10 (Tailscale, corporate VPN tunnels): mDNS peers share a link, so those rarely reach us."""
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    kept = [a for a in addresses if ipaddress.ip_address(a) not in cgnat]
    return kept or addresses


def service_name(hostname: str | None = None) -> str:
    host = (hostname or socket.gethostname()).split(".")[0]
    return f"Brasscribe on {host}"


def service_info(port: int, addresses: list[str], hostname: str | None = None):
    from zeroconf import ServiceInfo

    host = (hostname or socket.gethostname()).split(".")[0]
    return ServiceInfo(
        SERVICE_TYPE,
        f"{service_name(host)}.{SERVICE_TYPE}",
        port=port,
        addresses=[socket.inet_aton(a) for a in addresses],
        server=f"{host}.local.",
        properties={"v": __version__, "api": "/v1", "auth": "pair"},
    )


@contextmanager
def advertise(port: int, addresses: list[str]) -> Iterator[str | None]:
    """Register the service for the duration of the block; yields the advertised name, or None if it failed."""
    if not addresses:
        yield None
        return
    try:
        from zeroconf import IPVersion, Zeroconf

        zc = Zeroconf(ip_version=IPVersion.V4Only)
        info = service_info(port, lan_only(addresses))
        zc.register_service(info, allow_name_change=True)
    except Exception as e:  # discovery is a convenience; the engine still serves without it
        print(f"LAN discovery unavailable: {e}", flush=True)
        yield None
        return
    try:
        yield info.name.removesuffix(f".{SERVICE_TYPE}")
    finally:
        zc.unregister_service(info)
        zc.close()
