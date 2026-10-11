"""Checks on every request before it reaches a route: the Host name a trusted client used, and where a
state-changing request comes from.

Clients on this computer are trusted by address (api.py). A web page open in a browser on this computer can
send requests to that address too, and it must not count as a client the owner chose:

- A page from another site that sends a request carries that site in its Origin header (and, in current
  browsers, `Sec-Fetch-Site: cross-site` or `same-site`). POST, PUT, PATCH and DELETE are refused (403) when
  Origin names anything but the engine itself, or when Sec-Fetch-Site says the request comes from another site.
- A page loaded under some DNS name that resolves to this computer talks to the engine as its own origin,
  but its Host header carries that name. A request trusted by its address must name the engine by an IP
  address, localhost, a .local name, this computer's host name, or a name in BRASSCRIBE_ALLOWED_HOSTS (for
  a proxy on this computer); anything else gets 400.

Request bodies are capped (BRASSCRIBE_MAX_UPLOAD_BYTES, 2 GiB by default): a larger one gets 413, from its
Content-Length before it is read, or as soon as a body sent without one passes the cap.

Studio is served by the engine, so its requests are same-origin. The native apps send neither Origin nor
Sec-Fetch headers and are not affected; LAN clients authenticate with a token, so their Host is not checked.
"""

from __future__ import annotations

import functools
import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
DEFAULT_PORTS = {"http": "80", "https": "443"}


@functools.lru_cache(maxsize=1)
def own_names() -> frozenset[str]:
    """This computer's host names, as a client on it may type them."""
    name = socket.gethostname().rstrip(".").lower()  # no reverse DNS lookup: it can stall a request
    return frozenset({name, name.split(".")[0]} - {""})


def host_name(host: str) -> str:
    """The name part of a Host header: no port, no IPv6 brackets, no trailing dot, lower case."""
    host = host.strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    if host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    return host.rstrip(".")


def host_allowed(host: str, extra: Iterable[str] = ()) -> bool:
    name = host_name(host)
    try:
        ipaddress.ip_address(name)
        return True  # an address names the machine itself; only a DNS name can point somewhere else later
    except ValueError:
        pass
    return (name == "localhost" or name.endswith((".localhost", ".local")) or name in extra
            or name in own_names())


def same_origin(origin: str, host: str) -> bool:
    parts = urlsplit(origin)
    if parts.scheme not in DEFAULT_PORTS or not parts.netloc:
        return False

    def plain(netloc: str) -> str:
        netloc = netloc.lower()
        default = f":{DEFAULT_PORTS[parts.scheme]}"
        return netloc[: -len(default)] if netloc.endswith(default) else netloc

    return plain(parts.netloc) == plain(host.strip())


class RequestGuard:
    """ASGI middleware. `trusted(client_host)` says whether a client is trusted by its address right now."""

    def __init__(self, app, *, trusted: Callable[[str], bool], allowed_hosts: Iterable[str] = ()):
        self.app = app
        self.trusted = trusted
        self.allowed_hosts = frozenset(h.strip().rstrip(".").lower() for h in allowed_hosts if h.strip())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host")
        client = scope.get("client")[0] if scope.get("client") else ""
        if host is not None and self.trusted(client) and not host_allowed(host, self.allowed_hosts):
            return await JSONResponse({"detail": f"unknown host name {host_name(host)!r}; add it to "
                                                 "BRASSCRIBE_ALLOWED_HOSTS if it is this computer"},
                                      status_code=400)(scope, receive, send)
        if scope["method"] in STATE_CHANGING:
            origin, site = headers.get("origin"), headers.get("sec-fetch-site")
            if site in ("cross-site", "same-site") or (origin is not None and not same_origin(origin, host or "")):
                return await JSONResponse({"detail": "requests from other web pages are not accepted"},
                                          status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)


class BodyLimit:
    """ASGI middleware: 413 for a request body over `max_bytes`."""

    def __init__(self, app, *, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in STATE_CHANGING:
            return await self.app(scope, receive, send)
        too_large = f"the request is larger than {self.max_bytes} bytes (BRASSCRIBE_MAX_UPLOAD_BYTES)"
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            return await JSONResponse({"detail": too_large}, status_code=413)(scope, receive, send)
        received = 0

        async def counted():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(413, too_large)
            return message

        return await self.app(scope, counted, send)
