"""Which eval songs become conformance cases.

    uv run python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from brasscribe_conformance import cases


def song(root: Path, eval_set: str, name: str, files: tuple[str, ...], quarter: bool = False) -> None:
    d = root / "eval" / eval_set / name
    d.mkdir(parents=True)
    note = {"pitch": 60, "onset": 0.0, "offset": 0.5, **({"quarter": 0.0, "dur_quarter": 1.0} if quarter else {})}
    (d / "reference.json").write_text(json.dumps({"notes": [note]}))
    for f in files:
        (d / f).write_text("")


class EvalSongs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"
        patch = mock.patch.object(cases, "DATA", self.data)
        patch.start()
        self.addCleanup(patch.stop)
        self.work = Path(tmp.name) / "work"
        tab_files = ("alone.beats", "alone-sw.mid", "alone-bp.mid")
        song(self.data, "brass", "hymn", cases.ARRANGE_INPUTS, quarter=True)
        song(self.data, "guitarset", "take-1", tab_files)
        song(self.data, "guitarset", "take-2", tab_files)
        song(self.data, "half", "no-beats", ("muscriptor-medium.mid", "basic-pitch.mid"), quarter=True)

    def ids(self, only: str | None = None, skipped: dict | None = None) -> list[str]:
        return [c.id for c in cases.all_cases(self.work, only, skipped) if not c.id.startswith("talking/")]

    def test_a_song_with_its_inputs_is_arranged_every_way(self):
        self.assertEqual(self.ids("brass/"), ["brass/hymn/song", "brass/hymn/lead", "brass/hymn/layers",
                                              "brass/hymn/bench", "brass/hymn/quant"])

    def test_a_song_without_its_inputs_gives_no_case_that_reads_them(self):
        skipped: dict = {}
        ids = self.ids(skipped=skipped)
        self.assertEqual([i for i in ids if i.startswith("guitarset/")], [])
        self.assertEqual([i for i in ids if i.startswith("half/")], ["half/no-beats/bench"])  # the reference is enough
        self.assertEqual(skipped, {"guitarset": [("take-1", cases.ARRANGE_INPUTS), ("take-2", cases.ARRANGE_INPUTS)],
                                   "half": [("no-beats", ("beat-this.beats",))]})
        for c in cases.all_cases(self.work):
            if c.id.split("/")[0] not in ("brass", "guitarset", "half"):
                continue
            for v in c.args.values():
                for p in v if isinstance(v, list) else [v]:
                    if isinstance(p, Path) and p.is_relative_to(self.data):
                        self.assertTrue(p.exists(), f"{c.id} reads {p.name}, which is not there")

    def test_the_skipped_songs_are_named_once_per_set(self):
        skipped: dict = {}
        self.ids(skipped=skipped)
        self.assertEqual(cases.skipped_lines(skipped), [
            "SKIP guitarset: 2 songs without beat-this.beats, muscriptor-medium.mid, basic-pitch.mid: "
            "not arranged, so not compared",
            "SKIP half: 1 song without beat-this.beats: not arranged, so not compared"])

    def test_only_filters_the_skipped_songs_too(self):
        skipped: dict = {}
        self.ids("brass/", skipped)
        self.assertEqual(skipped, {})


if __name__ == "__main__":
    unittest.main()
