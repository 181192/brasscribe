#!/usr/bin/env python3
"""Print pip requirement lines, with every published hash, for packages named in a uv.lock.

    .github/scripts/lock-requirements.py sounds/uv.lock mido packaging > requirements.txt
    pip install --require-hashes -r requirements.txt

For a CI step that needs one or two packages of a project and not its whole environment: the versions and the
sha256 of every file are the lock's, so pip refuses anything else. Exit 1 when a package is not in the lock or
has no hash there. Standard library only, and no tomllib, so any python3 on a runner will do.
"""

from __future__ import annotations

import re
import sys


def requirement(lock: str, name: str) -> str:
    for block in lock.split("[[package]]")[1:]:
        if re.search(rf'^name = "{re.escape(name)}"$', block, re.M):
            version = re.search(r'^version = "([^"]+)"$', block, re.M)
            hashes = sorted(set(re.findall(r'hash = "(sha256:[0-9a-f]{64})"', block)))
            if not version or not hashes:
                raise SystemExit(f"{name} has no version or no hash in the lock")
            return f"{name}=={version.group(1)} " + " ".join(f"--hash={h}" for h in hashes)
    raise SystemExit(f"{name} is not in the lock")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    lock = open(argv[1], encoding="utf-8").read()
    for name in argv[2:]:
        print(requirement(lock, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
