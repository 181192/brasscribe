"""Content hashes for files, file sets and source code.

File hashes are memoised on (path, size, mtime) in a small JSON index, so
re-hashing a 1.5 GB checkpoint or 260 MB of stems on every run is avoided.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode())


def _sha256_file_raw(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


class HashIndex:
    """sha256 per file, memoised on (resolved path, size, mtime_ns)."""

    def __init__(self, index_file: Path | None = None):
        self.index_file = index_file
        self._lock = threading.Lock()
        self._memo: dict[str, list] = {}
        if index_file and index_file.exists():
            try:
                self._memo = json.loads(index_file.read_text())
            except (OSError, ValueError):
                self._memo = {}

    def file(self, path: Path) -> str:
        path = Path(path)
        st = path.stat()
        key = str(path.resolve())
        stamp = [st.st_size, st.st_mtime_ns]
        with self._lock:
            hit = self._memo.get(key)
            if hit and hit[:2] == stamp:
                return hit[2]
        digest = _sha256_file_raw(path)
        with self._lock:
            self._memo[key] = [*stamp, digest]
        return digest

    def files(self, root: Path) -> dict[str, str]:
        """Relative path -> sha256 for every regular file under root."""
        root = Path(root)
        return {p.relative_to(root).as_posix(): self.file(p) for p in sorted(root.rglob("*")) if p.is_file()}

    def save(self) -> None:
        if not self.index_file:
            return
        with self._lock:
            data = json.dumps(self._memo)
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_file.with_suffix(".tmp")
        tmp.write_text(data)
        tmp.replace(self.index_file)


def digest_of_files(files: dict[str, str]) -> str:
    """One digest for a set of files (relative path -> sha256)."""
    return sha256_json(sorted(files.items()))


def source_fingerprint(*roots: Path) -> str:
    """Digest of all Python sources under the given package directories or files."""
    h = hashlib.sha256()
    for root in roots:
        root = Path(root)
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
        for p in files:
            h.update((p.relative_to(root).as_posix() if root.is_dir() else p.name).encode())
            h.update(p.read_bytes())
    return h.hexdigest()
