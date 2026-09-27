"""Companion-mode credentials: a stable server identity, one long-lived credential per paired device,
the pairing window and approve-on-the-computer requests.

State lives in the companion state directory (BRASSCRIBE_STATE, default <data>/companion):

    server.json   {"server_id", "created_at"}: random, kept across restarts and address or port changes
    devices.json  {"devices": [...]}: one entry per paired device; tokens are stored only as SHA-256

A device pairs once. Its token stays valid until the device is revoked, the server is reset, or the
device has not been seen for `idle_days`. A device may rotate its token; the token it rotated with
keeps working until the new one is first used (at most `grace_s`, 30 days), so a lost response, or a
retry with the old token, cannot lock the device out. Files are rewritten atomically under a cross-process
lock and re-read when they change on disk, so `brasscribe devices revoke` takes effect in a running engine
and is never undone by the engine's own writes. `last_seen` (presence) is tracked in memory on every request
and flushed at most once a minute.

The server id is a routing identifier (it lets a client match a rediscovered engine to its stored
credential), not proof of identity: over plain HTTP anyone can claim it. Proof comes from a pinned
TLS key fingerprint, which the pairing payload reserves as `fp`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, TypeVar
from urllib.parse import quote, urlencode

PAIRING_PAYLOAD_VERSION = 1
CODE_DIGITS = 6
WINDOW_S = 600.0  # a pairing window opened on the computer
REQUEST_S = 120.0  # an approve-on-the-computer request waits this long
MAX_PENDING = 3
LOCK_AFTER = 5  # wrong codes before pairing locks
LOCK_BASE_S = 30.0
LOCK_MAX_S = 900.0
SEEN_FLUSH_S = 60.0  # last_seen is kept in memory and written to disk at most this often
ONLINE_S = 60.0  # a device seen this recently is online (apps send a heartbeat every 20 s)
NAME_MAX = 64

Clock = Callable[[], float]
T = TypeVar("T")


def iso(t: float | None) -> str:
    return "" if t is None else datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def clean_name(name: str | None, fallback: str = "Unnamed device") -> str:
    """Device names are shown on the computer: no control characters, one line, at most 64 characters."""
    text = "".join(" " if unicodedata.category(c)[0] in "CZ" else c for c in (name or ""))
    text = " ".join(text.split())[:NAME_MAX].strip()
    return text or fallback


def write_private(path: Path, data: dict) -> None:
    """Write JSON atomically, readable only by the owner (on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------- server identity


@dataclass
class ServerIdentity:
    server_id: str
    created_at: float

    @classmethod
    def load(cls, state_dir: Path, clock: Clock = time.time) -> ServerIdentity:
        path = state_dir / "server.json"
        try:
            d = json.loads(path.read_text())
            return cls(str(d["server_id"]), float(d["created_at"]))
        except (OSError, ValueError, KeyError, TypeError):
            ident = cls(secrets.token_hex(16), clock())
            write_private(path, asdict(ident))
            return ident


# ---------------------------------------------------------------------------- devices


@dataclass
class Device:
    device_id: str
    name: str
    platform: str
    paired_at: float
    last_seen: float
    token_hash: str
    rotated_at: float | None = None
    prev_hash: str | None = None
    prev_until: float | None = None

    def public(self) -> dict:
        return {"device_id": self.device_id, "name": self.name, "platform": self.platform,
                "paired_at": iso(self.paired_at), "last_seen": iso(self.last_seen),
                "rotated_at": iso(self.rotated_at) if self.rotated_at else None}


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Exclusive lock shared with other processes (the engine and `brasscribe devices`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)  # retries for about 10 s, then raises
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


class DeviceRegistry:
    """Paired devices, shared by the running engine and `brasscribe devices` in another process.

    Every change takes a cross-process file lock, re-reads the file, applies the change and writes it back,
    so a CLI revoke is never overwritten by the engine's own write. `last_seen` is updated in memory on every
    authenticated request (that is what `online` is computed from) and flushed to disk at most every
    `SEEN_FLUSH_S`; unflushed values never bring back a device the file no longer has.
    """

    def __init__(self, path: Path, *, idle_days: float = 180.0, grace_s: float = 30 * 86400.0, clock: Clock = time.time):
        self.path = path
        self.idle_s = idle_days * 86400.0
        self.grace_s = grace_s
        self.clock = clock
        self.lock = threading.Lock()
        self._devices: dict[str, Device] = {}
        self._stamp: tuple[int, int, int] | None = None
        self._seen: dict[str, float] = {}  # last_seen newer than the file, per device id
        self._flushed_at = clock()
        with self.lock:
            self._reload()

    # -- persistence (call with self.lock held)

    def _disk_stamp(self) -> tuple[int, int, int] | None:
        try:
            st = self.path.stat()
            return st.st_ino, st.st_mtime_ns, st.st_size  # an atomic replace always changes the inode
        except OSError:
            return None

    def _read(self) -> None:
        """Load the file if another process changed it, laying unflushed last_seen values over it."""
        stamp = self._disk_stamp()
        if stamp is not None and stamp == self._stamp:
            return
        devices: dict[str, Device] = {}
        if stamp is not None:
            try:
                for d in json.loads(self.path.read_text()).get("devices", []):
                    dev = Device(**d)
                    devices[dev.device_id] = dev
            except (OSError, ValueError, TypeError):
                devices = {}
        self._seen = {k: t for k, t in self._seen.items() if k in devices}  # revoked elsewhere: gone
        for k, t in self._seen.items():
            devices[k].last_seen = max(devices[k].last_seen, t)
        self._devices, self._stamp = devices, stamp

    def _reload(self) -> None:
        self._read()
        if self._stale():
            self._write(self._prune)

    def _write(self, change: Callable[[], T]) -> T:
        """Read-modify-write under the cross-process lock; also flushes every unflushed last_seen."""
        with file_lock(self.path.with_name(self.path.name + ".lock")):
            self._read()
            result = change()
            write_private(self.path, {"devices": [asdict(d) for d in self._devices.values()]})
            self._stamp = self._disk_stamp()
            self._seen = {}
            self._flushed_at = self.clock()
            return result

    def _stale(self) -> list[str]:
        now = self.clock()
        return [k for k, d in self._devices.items() if now - d.last_seen > self.idle_s]

    def _prune(self) -> None:
        for k in self._stale():
            del self._devices[k]

    def flush(self) -> None:
        """Write last_seen values not yet on disk (periodically on use, and when the engine stops)."""
        with self.lock:
            if self._seen:
                self._write(lambda: None)

    # -- presence

    def is_online(self, device: Device) -> bool:
        return self.clock() - device.last_seen <= ONLINE_S

    def public(self, device: Device) -> dict:
        return {**device.public(), "online": self.is_online(device)}

    # -- operations

    def pair(self, name: str | None, platform: str | None = None, *, replace: str | None = None) -> tuple[Device, str]:
        """New credential. With `replace`, the device keeps its id and entry and only its token changes."""
        token = secrets.token_urlsafe(32)
        now = self.clock()

        def change() -> Device:
            old = self._devices.get(replace) if replace else None
            if old:
                old.token_hash, old.prev_hash, old.prev_until = token_hash(token), None, None
                old.name, old.last_seen, old.rotated_at = clean_name(name, old.name), now, now
                return old
            dev = Device(secrets.token_hex(8), clean_name(name), clean_name(platform, "unknown")[:24], now, now,
                         token_hash(token))
            self._devices[dev.device_id] = dev
            return dev

        with self.lock:
            return self._write(change), token

    def authenticate(self, token: str) -> Device | None:
        h = token_hash(token)
        now = self.clock()
        with self.lock:
            self._reload()
            for dev in self._devices.values():
                current = hmac.compare_digest(h, dev.token_hash)
                previous = (dev.prev_hash is not None and dev.prev_until is not None and now < dev.prev_until
                            and hmac.compare_digest(h, dev.prev_hash))
                if current or previous:
                    break
            else:
                return None
            device_id = dev.device_id
            if now - dev.last_seen > self.idle_s:
                self._write(lambda: self._devices.pop(device_id, None))
                return None
            dev.last_seen = self._seen[device_id] = now
            if current and dev.prev_hash:  # the new token arrived: the old one is done

                def retire() -> None:
                    d = self._devices.get(device_id)
                    if d:
                        d.prev_hash = d.prev_until = None

                self._write(retire)
            elif now - self._flushed_at >= SEEN_FLUSH_S:
                self._write(lambda: None)
            return self._devices.get(device_id)  # None when revoked by another process meanwhile

    def rotate(self, device_id: str, presented: str | None = None) -> str | None:
        """New token for the device. The token the device rotated with (`presented`, else the current one)
        stays valid until the new one is used, so a retry after a lost response still works."""
        token = secrets.token_urlsafe(32)
        now = self.clock()

        def change() -> bool:
            dev = self._devices.get(device_id)
            if not dev:
                return False
            dev.prev_hash = token_hash(presented) if presented else dev.token_hash
            dev.prev_until = now + self.grace_s
            dev.token_hash, dev.rotated_at, dev.last_seen = token_hash(token), now, now
            return True

        with self.lock:
            return token if self._write(change) else None

    def revoke(self, device_id: str) -> bool:
        with self.lock:
            return self._write(lambda: self._devices.pop(device_id, None)) is not None

    def revoke_all(self) -> int:
        def change() -> int:
            n = len(self._devices)
            self._devices = {}
            return n

        with self.lock:
            return self._write(change)

    def get(self, device_id: str) -> Device | None:
        with self.lock:
            self._reload()
            return self._devices.get(device_id)

    def list(self) -> list[Device]:
        with self.lock:
            self._reload()
            return sorted(self._devices.values(), key=lambda d: d.paired_at)


def reset_server(state_dir: Path, clock: Clock = time.time) -> ServerIdentity:
    """Forget every paired device and take a new server id: every device must pair again."""
    DeviceRegistry(state_dir / "devices.json", clock=clock).revoke_all()
    (state_dir / "server.json").unlink(missing_ok=True)
    return ServerIdentity.load(state_dir, clock)


# ---------------------------------------------------------------------------- pairing window


@dataclass
class PairingWindow:
    """The code a new device types (or scans). Wrong codes lock pairing for a while; the code itself never
    changes behind the user's back, so the code on screen stays the one that works."""

    code: str | None = field(default_factory=new_code)
    expires_at: float | None = None  # None: until closed
    single_use: bool = False
    failures: int = 0
    lockouts: int = 0
    locked_until: float = 0.0
    clock: Clock = time.time
    lock: threading.Lock = field(default_factory=threading.Lock)

    def open(self, ttl: float | None = WINDOW_S, single_use: bool = True) -> str:
        with self.lock:
            self.code = new_code()
            self.expires_at = None if ttl is None else self.clock() + ttl
            self.single_use = single_use
            self.failures = 0
            return self.code

    def extend(self, ttl: float = WINDOW_S) -> bool:
        with self.lock:
            if not self.is_open_locked():
                return False
            self.expires_at = self.clock() + ttl
            return True

    def close(self) -> None:
        with self.lock:
            self.code, self.expires_at = None, None

    def is_open_locked(self) -> bool:
        return self.code is not None and (self.expires_at is None or self.clock() < self.expires_at)

    @property
    def is_open(self) -> bool:
        with self.lock:
            return self.is_open_locked()

    def retry_after(self) -> float:
        return max(0.0, self.locked_until - self.clock())

    def check(self, code: str) -> str:
        """'ok', 'wrong', 'locked' or 'closed'."""
        with self.lock:
            if self.clock() < self.locked_until:
                return "locked"
            if not self.is_open_locked():
                return "closed"
            if hmac.compare_digest(code.strip().replace(" ", "").encode(), self.code.encode()):
                self.failures = self.lockouts = 0
                if self.single_use:
                    self.code, self.expires_at = None, None
                return "ok"
            self.failures += 1
            if self.failures >= LOCK_AFTER:
                self.failures = 0
                self.locked_until = self.clock() + min(LOCK_MAX_S, LOCK_BASE_S * 2 ** self.lockouts)
                self.lockouts += 1
            return "wrong"


# ---------------------------------------------------------------------------- approve on the computer


@dataclass
class PairRequestEntry:
    request_id: str
    name: str
    platform: str
    match_code: str  # shown on both screens so the owner can tell which phone is asking
    created: float
    status: str = "pending"  # pending | approved | denied
    token: str | None = None
    device_id: str | None = None

    def public(self) -> dict:
        return {"request_id": self.request_id, "name": self.name, "platform": self.platform,
                "match_code": self.match_code, "created_at": iso(self.created), "status": self.status}


class PairRequests:
    """A device asks to pair without a code; the owner allows or denies it on the computer."""

    def __init__(self, clock: Clock = time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self._items: dict[str, PairRequestEntry] = {}

    def _expire(self) -> None:
        now = self.clock()
        for k in [k for k, r in self._items.items() if now - r.created > REQUEST_S]:
            del self._items[k]

    def create(self, name: str | None, platform: str | None) -> PairRequestEntry | None:
        with self.lock:
            self._expire()
            if sum(r.status == "pending" for r in self._items.values()) >= MAX_PENDING:
                return None
            r = PairRequestEntry(secrets.token_urlsafe(24), clean_name(name), clean_name(platform, "unknown")[:24],
                                 f"{secrets.randbelow(10**4):04d}", self.clock())
            self._items[r.request_id] = r
            return r

    def pending(self) -> list[PairRequestEntry]:
        with self.lock:
            self._expire()
            return [r for r in self._items.values() if r.status == "pending"]

    def decide(self, request_id: str, approve: bool, registry: DeviceRegistry) -> PairRequestEntry | None:
        with self.lock:
            self._expire()
            r = self._items.get(request_id)
            if not r or r.status != "pending":
                return None
            if approve:
                dev, token = registry.pair(r.name, r.platform)
                r.status, r.token, r.device_id = "approved", token, dev.device_id
            else:
                r.status = "denied"
            return r

    def poll(self, request_id: str) -> PairRequestEntry | None:
        """The requesting device's view. An approved request hands out its token once and is then forgotten."""
        with self.lock:
            self._expire()
            r = self._items.get(request_id)
            if r and r.status != "pending":
                del self._items[request_id]
            return r


# ---------------------------------------------------------------------------- pairing payload


def pairing_uri(server_id: str, name: str, hosts: list[str], code: str | None, fingerprint: str | None = None) -> str:
    """brasscribe://pair?v=1&id=<server_id>&name=<name>&h=<ip:port>[,<ip:port>]&code=<digits>[&fp=<spki sha256>]"""
    q: dict[str, str] = {"v": str(PAIRING_PAYLOAD_VERSION), "id": server_id, "name": name}
    if hosts:
        q["h"] = ",".join(hosts)
    if code:
        q["code"] = code
    if fingerprint:
        q["fp"] = fingerprint
    return "brasscribe://pair?" + urlencode(q, quote_via=quote, safe=":,")
