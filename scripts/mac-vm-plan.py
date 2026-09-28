#!/usr/bin/env python3
"""Split the macOS UI tests over N VMs (scripts/mac-vm.sh test-ui).

usage: mac-vm-plan.py N ONLY DURATIONS SOURCES
  ONLY       comma-separated Class or Class/testName filters ("" for every test)
  DURATIONS  build/mac-vm/durations.json from earlier runs ({"Class/test": seconds}); may be missing
  SOURCES    apps/apple/AppUITests

Prints N lines, one per VM: space-separated Class/test ids (a line may be empty). The longest tests
are placed first, each on the VM with the least work so far; a test without a timing counts 20 s.
"""
import json
import pathlib
import re
import sys

n, only, durations, sources = int(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4])
filters = [f.strip().removeprefix("BrasscribePlayUITests_macOS/") for f in only.split(",") if f.strip()]
known = json.loads(durations.read_text()) if durations.exists() else {}

tests = []
for f in sorted(sources.glob("*.swift")):
    text = f.read_text()
    head = text.split("class ", 1)[0]
    if "#if os(iOS)" in head:
        continue  # the phone-only classes
    cls = None
    for line in text.splitlines():
        m = re.match(r"\s*(?:final\s+)?class\s+(\w+)\s*:\s*XCTestCase", line)
        if m:
            cls = m.group(1)
        m = re.match(r"\s*func\s+(test\w+)\s*\(\s*\)", line)
        if m and cls:
            tests.append(f"{cls}/{m.group(1)}")

if filters:
    tests = [t for t in tests if any(t == f or t.startswith(f + "/") or t.split("/")[0] == f for f in filters)]

load = [0.0] * n
shards = [[] for _ in range(n)]
for t in sorted(tests, key=lambda t: -known.get(t, 20.0)):
    i = load.index(min(load))
    shards[i].append(t)
    load[i] += known.get(t, 20.0)
for s in shards:
    print(" ".join(s))
