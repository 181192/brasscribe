"""DNS-SD (Bonjour/mDNS) advertisement so Play apps on the LAN can find the engine.

The advertisement says where the engine is and which engine it is (`id`, the stable server id), so a paired
client can find its engine again after the address or port changes. Clients still pair before they are trusted.

The display name is "Brasscribe on <computer>". <computer> is BRASSCRIBE_COMPUTER_NAME when set (the desktop
helper passes the user-visible name: macOS ComputerName, the Windows device name), else the operating system's
computer name (macOS `scutil --get ComputerName`), else the short host name. BRASSCRIBE_SERVER_NAME replaces
the whole display name. /v1/health, the pairing response and the pairing payload use the same name.
The TXT record carries it as `host`, so apps can localise the label ("Brasscribe på <computer>"); the mDNS
instance name may gain a " (2)" suffix on collision, so apps show `host`, not the instance name.
"""

from __future__ import annotations

import functools
import ipaddress
import os
import shutil
import socket
import subprocess
import sys
from contextlib import contextmanager
from typing import Iterator

from . import __version__

SERVICE_TYPE = "_brasscribe._tcp.local."


def lan_only(addresses: list[str]) -> list[str]:
    """Drop 100.64.0.0/10 (Tailscale, corporate VPN tunnels): mDNS peers share a link, so those rarely reach us."""
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    kept = [a for a in addresses if ipaddress.ip_address(a) not in cgnat]
    return kept or addresses


INSTANCE_MAX_BYTES = 63  # one DNS label
PREFIX = "Brasscribe on "


def host_label(hostname: str | None = None) -> str:
    """DNS-safe short host name for the SRV target."""
    host = (hostname or socket.gethostname()).split(".")[0]
    return "".join(c if c.isascii() and (c.isalnum() or c == "-") else "-" for c in host).strip("-") or "brasscribe"


@functools.lru_cache(maxsize=1)
def os_computer_name() -> str | None:
    """The name the operating system shows for this computer, where it differs from the host name.

    macOS: the ComputerName ("Kari's MacBook Pro"), which the host name only approximates. Windows: the
    device name is the host name, which socket.gethostname() already returns with its case kept.
    """
    if sys.platform != "darwin" or not shutil.which("scutil"):
        return None
    try:
        out = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _fit(text: str, room: int) -> str:
    return text.encode()[:room].decode(errors="ignore").strip()


def computer_name(hostname: str | None = None) -> str:
    """The name people know the computer by, cut so "Brasscribe on <name>" fits one DNS label (63 bytes).

    BRASSCRIBE_COMPUTER_NAME, else the operating system's computer name, else the short host name. With an
    explicit `hostname`, only that is used."""
    from .companion import clean_name

    raw = ""
    if hostname is None:
        raw = os.environ.get("BRASSCRIBE_COMPUTER_NAME", "").strip() or os_computer_name() or ""
    name = clean_name(raw.replace(".", " "), fallback="") if raw else (hostname or socket.gethostname()).split(".")[0]
    return _fit(name, INSTANCE_MAX_BYTES - len(PREFIX.encode())) or host_label(hostname)


def server_names(hostname: str | None = None) -> tuple[str, str]:
    """(server name, computer name part). The server name is "Brasscribe on <computer>" unless
    BRASSCRIBE_SERVER_NAME replaces it whole; the part is what follows "Brasscribe on ", or the whole
    override when it has no such prefix. Both fit one DNS label, so the mDNS instance name is the same."""
    override = os.environ.get("BRASSCRIBE_SERVER_NAME", "").strip() if hostname is None else ""
    if override:
        from .companion import clean_name

        full = _fit(clean_name(override.replace(".", " "), fallback=""), INSTANCE_MAX_BYTES)
        if full:
            return full, (full.removeprefix(PREFIX).strip() or full)
    name = computer_name(hostname)
    return PREFIX + name, name


def service_name(hostname: str | None = None) -> str:
    return server_names(hostname)[0]


def service_info(port: int, addresses: list[str], hostname: str | None = None, server_id: str | None = None):
    from zeroconf import ServiceInfo

    full, name = server_names(hostname)
    return ServiceInfo(
        SERVICE_TYPE,
        f"{full}.{SERVICE_TYPE}",
        port=port,
        addresses=[socket.inet_aton(a) for a in addresses],
        server=f"{host_label(hostname)}.local.",
        properties={"v": __version__, "api": "/v1", "auth": "pair", "host": name,
                    **({"id": server_id} if server_id else {})},
    )


@contextmanager
def advertise(port: int, addresses: list[str], server_id: str | None = None) -> Iterator[str | None]:
    """Register the service for the duration of the block; yields the advertised name, or None if it failed."""
    if not addresses:
        yield None
        return
    try:
        from zeroconf import IPVersion, Zeroconf

        zc = Zeroconf(ip_version=IPVersion.V4Only)
        info = service_info(port, lan_only(addresses), server_id=server_id)
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
