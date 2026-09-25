"""Content-addressed artifact cache.

A stage's cache key is a digest of everything that determines its output:
stage name, parameters, the content hashes of its inputs, and fingerprints of
the code and adapter environment that run it. The entry under that key holds
the stage's output files plus `entry.json` (file hashes, provenance).

Entries are written once and made read-only. Runs get their copy by hardlink
(same filesystem) or copy-on-write clone, so a 260 MB stem set costs no space
per run. Imports from an existing directory are cloned, never hardlinked, so
making the entry read-only never touches the source files.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .hashing import HashIndex, digest_of_files


@dataclass
class Entry:
    key: str
    stage: str
    files: dict[str, str]  # relative path -> sha256
    created: float = field(default_factory=time.time)
    provenance: dict = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return digest_of_files(self.files)


def clone_file(src: Path, dst: Path) -> None:
    """Copy-on-write clone where the filesystem supports it (APFS, btrfs, XFS), else a plain copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        if subprocess.run(["cp", "-c", str(src), str(dst)], capture_output=True).returncode == 0:
            return
    elif sys.platform.startswith("linux"):
        if subprocess.run(["cp", "--reflink=auto", str(src), str(dst)], capture_output=True).returncode == 0:
            return
    shutil.copy2(src, dst)


def link_or_clone(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        clone_file(src, dst)


def _read_only(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


class ArtifactCache:
    def __init__(self, root: Path, hashes: HashIndex | None = None):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.hashes = hashes or HashIndex(self.root / "file-hashes.json")

    def _dir(self, key: str) -> Path:
        return self.objects / key[:2] / key

    def lookup(self, key: str) -> Entry | None:
        meta = self._dir(key) / "entry.json"
        if not meta.exists():
            return None
        d = json.loads(meta.read_text())
        return Entry(d["key"], d["stage"], d["files"], d.get("created", 0.0), d.get("provenance", {}))

    def path(self, entry: Entry, rel: str) -> Path:
        return self._dir(entry.key) / "files" / rel

    def store(self, key: str, stage: str, src: Path, files: list[str] | None = None, provenance: dict | None = None) -> Entry:
        """Store files from src (all regular files, or the given relative paths) under key."""
        src = Path(src)
        rels = files if files is not None else [p.relative_to(src).as_posix() for p in sorted(src.rglob("*")) if p.is_file()]
        final = self._dir(key)
        if final.exists():
            existing = self.lookup(key)
            if existing:
                return existing
        tmp = final.parent / f".{key}.{uuid.uuid4().hex}.tmp"
        (tmp / "files").mkdir(parents=True)
        hashes = {}
        for rel in rels:
            dst = tmp / "files" / rel
            clone_file(src / rel, dst)
            _read_only(dst)
            hashes[rel] = self.hashes.file(dst)
        entry = Entry(key, stage, hashes, provenance=provenance or {})
        (tmp / "entry.json").write_text(json.dumps(asdict(entry), indent=1, sort_keys=True))
        try:
            tmp.rename(final)
        except OSError:
            # Another writer stored the same key first; theirs is equivalent.
            shutil.rmtree(tmp, ignore_errors=True)
            return self.lookup(key)  # type: ignore[return-value]
        self.hashes.save()
        return entry

    def materialize(self, entry: Entry, dest: Path) -> None:
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for rel in entry.files:
            link_or_clone(self.path(entry, rel), dest / rel)

    def verify(self, entry: Entry) -> list[str]:
        """Relative paths whose content no longer matches the recorded hash."""
        bad = []
        for rel, digest in entry.files.items():
            p = self.path(entry, rel)
            if not p.exists() or self.hashes.file(p) != digest:
                bad.append(rel)
        return bad

    def evict(self, key: str) -> None:
        d = self._dir(key)
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file():
                    p.chmod(p.stat().st_mode | stat.S_IWUSR)
            shutil.rmtree(d)
