"""Score a finished blind A/B test.

    uv run --project sounds python sounds/ab-test/score.py data/runs/sound/ab-test

Reads listener-N/answers.csv and key.json. Reports the share of judgements preferring the
realistic tier, per listener and per excerpt, with a one-sided exact binomial p-value
against chance (50%). The acceptance bar in docs/plan/apps-plan.md is 80%, i.e. at least
20 of 25 judgements for 5 listeners x 5 excerpts.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def binom_tail(k: int, n: int) -> float:
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main() -> None:
    root = Path(sys.argv[1])
    key = json.loads((root / "key.json").read_text())["listeners"]
    total, wins = 0, 0
    per_excerpt = defaultdict(lambda: [0, 0])
    for listener, pairs in sorted(key.items(), key=lambda kv: int(kv[0])):
        sheet = root / f"listener-{listener}" / "answers.csv"
        with sheet.open() as f:
            rows = list(csv.reader(f))[1:]
        lw, ln = 0, 0
        for row in rows:
            if len(row) < 2 or row[1].strip().upper() not in ("A", "B"):
                continue
            pair = pairs[row[0].strip()]
            realistic = pair[row[1].strip().upper()] == "realistic"
            lw += realistic
            ln += 1
            per_excerpt[pair["excerpt"]][0] += realistic
            per_excerpt[pair["excerpt"]][1] += 1
        print(f"listener {listener}: realistic preferred {lw}/{ln}")
        wins, total = wins + lw, total + ln
    for ex, (w, n) in sorted(per_excerpt.items()):
        print(f"excerpt {ex}: {w}/{n}")
    if total:
        print(f"overall: {wins}/{total} = {wins / total:.0%}, one-sided binomial p = {binom_tail(wins, total):.4f}; "
              f"bar (80%): {'PASS' if wins / total >= 0.8 else 'FAIL'}")


if __name__ == "__main__":
    main()
