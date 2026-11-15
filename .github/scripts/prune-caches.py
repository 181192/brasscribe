#!/usr/bin/env python3
"""Deletes the Actions caches nothing reads any more, so the repository stays under its 10 GB and the caches that
are read (Verovio, the Rust builds, Gradle) are not evicted. Run by ci.yml after a push to main.

Deleted:
- on main, every older generation of a cache: the same key but for its hashes (a newer lock file, Cargo.lock,
  build script), keeping the newest of each;
- caches saved on a release tag and not read for a day: only a re-run of that release reads them.
Pull requests' caches are left alone: GitHub drops them after a week unread.

    prune-caches.py            delete (GH_TOKEN with actions: write, GITHUB_REPOSITORY)
    prune-caches.py --dry-run  only list what it would delete
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# A segment of a key that is a hash (hashFiles, a commit, rust-cache's hashes): eight or more hex digits.
HASH = re.compile(r"^[0-9a-f]{8,}$")
MAIN = "refs/heads/main"


def family(key: str) -> str:
    """The key with its hashes taken out: the generations of one cache share it."""
    return "-".join("*" if HASH.match(part) else part for part in key.split("-"))


def when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def stale(caches: list[dict], now: datetime) -> list[dict]:
    """The caches to delete, from the entries of GET /repos/{repo}/actions/caches."""
    newest: dict[str, dict] = {}
    out = []
    for cache in sorted(caches, key=lambda c: when(c["created_at"]), reverse=True):
        ref = cache["ref"]
        if ref == MAIN:
            fam = family(cache["key"])
            if fam in newest:
                out.append(cache)
            else:
                newest[fam] = cache
        elif ref.startswith("refs/tags/") and now - when(cache["last_accessed_at"]) > timedelta(days=1):
            out.append(cache)
    return out


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    dry = "--dry-run" in sys.argv[1:]
    repo = os.environ["GITHUB_REPOSITORY"]
    pages = gh("api", "--paginate", f"repos/{repo}/actions/caches?per_page=100", "--jq", ".actions_caches[]")
    caches = [json.loads(line) for line in pages.splitlines() if line.strip()]
    doomed = stale(caches, datetime.now(timezone.utc))
    total = sum(c["size_in_bytes"] for c in caches)
    freed = sum(c["size_in_bytes"] for c in doomed)
    print(f"{len(caches)} caches, {total / 2**30:.2f} GB; {len(doomed)} to delete, {freed / 2**30:.2f} GB")
    for cache in doomed:
        print(f"  {cache['size_in_bytes'] / 2**20:7.0f} MB  {cache['ref']}  {cache['key']}")
        if not dry:
            # Another run may have deleted it first, or GitHub evicted it: not an error.
            subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{repo}/actions/caches/{cache['id']}"],
                           check=False, capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
