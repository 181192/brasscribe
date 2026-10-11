"""Which eval songs become conformance cases.

    uv run python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scribe_conformance import cases


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
        song(self.data, "brass", "no-beats", ("muscriptor-medium.mid", "basic-pitch.mid"), quarter=True)

    def ids(self, only: str | None = None, skipped: dict | None = None) -> list[str]:
        return [c.id for c in cases.all_cases(self.work, only, skipped) if not c.id.startswith("talking/")]

    def test_a_song_with_its_inputs_is_arranged_every_way(self):
        self.assertEqual(self.ids("brass/hymn"), ["brass/hymn/song", "brass/hymn/lead", "brass/hymn/layers",
                                                  "brass/hymn/bench", "brass/hymn/quant"])
        self.assertEqual([cases.missing_files(c) for c in cases.all_cases(self.work, "brass/hymn")], [[]] * 5)

    def test_a_set_in_which_no_song_has_an_input_is_left_out(self):
        skipped: dict = {}
        ids = self.ids(skipped=skipped)
        self.assertEqual([i for i in ids if i.startswith("guitarset/")], [])
        self.assertEqual(skipped, {"guitarset": ["take-1", "take-2"]})
        self.assertEqual(cases.skipped_lines(skipped), [
            "SKIP guitarset: 2 songs, none with beat-this.beats, muscriptor-medium.mid, basic-pitch.mid: "
            "not arranged, so not compared"])

    def test_a_song_that_lost_a_file_in_a_set_that_is_arranged_keeps_its_cases_and_they_fail(self):
        skipped: dict = {}
        broken = {c.id: cases.missing_files(c) for c in cases.all_cases(self.work, "brass/no-beats", skipped)}
        self.assertEqual(skipped, {})  # never a quiet skip
        self.assertEqual(broken, {"brass/no-beats/song": ["beat-this.beats"], "brass/no-beats/lead": ["beat-this.beats"],
                                  "brass/no-beats/layers": ["beat-this.beats"], "brass/no-beats/bench": [],
                                  "brass/no-beats/quant": ["beat-this.beats"]})

    def test_only_filters_the_skipped_songs_too_also_by_a_whole_case_id(self):
        skipped: dict = {}
        self.ids("brass/", skipped)
        self.assertEqual(skipped, {})
        self.assertEqual(self.ids("guitarset/take-2/song", skipped), [])
        self.assertEqual(skipped, {"guitarset": ["take-2"]})


class BrokenInput(unittest.TestCase):
    """The runner on a song that lost its beats: its cases fail by name, the run goes on, and it exits non-zero."""

    def test_a_missing_input_fails_the_case_and_the_run_and_the_report_lists_the_skipped_songs(self):
        import contextlib
        import io
        import sys

        from scribe_conformance import run

        with tempfile.TemporaryDirectory() as tmp:
            data, work, report = Path(tmp) / "data", Path(tmp) / "work", Path(tmp) / "report.json"
            song(data, "brass", "x-tune", ("muscriptor-medium.mid", "basic-pitch.mid"))
            song(data, "brass", "whole", cases.ARRANGE_INPUTS)
            song(data, "guitarset", "x-tune", ("alone.beats",))
            out = io.StringIO()
            argv = ["run", "--work", str(work), "--only", "/x-tune", "--skip-python", "--report", str(report)]
            with mock.patch.object(cases, "DATA", data), mock.patch.object(run, "rust_bin", lambda: Path("unused")), \
                    mock.patch.object(run, "write_report", lambda work, results: work / "report.json"), \
                    mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
                run.main()
            self.assertEqual(exit_.exception.code, 1)
            self.assertIn("SKIP guitarset: 1 song, none with", out.getvalue())
            self.assertIn("DIFF brass/x-tune/song", out.getvalue())
            self.assertIn("inputs: missing: beat-this.beats", out.getvalue())
            self.assertIn("cases identical: 0/3", out.getvalue())
            rows = json.loads(report.read_text())
            self.assertEqual([r["case"] for r in rows],
                             ["brass/x-tune/song", "brass/x-tune/lead", "brass/x-tune/layers", "guitarset/x-tune"])
            self.assertTrue(all(r["checks"] == [{"file": "inputs", "ok": False, "detail": "missing: beat-this.beats"}]
                                for r in rows[:3]))
            self.assertEqual(rows[3]["skipped"], True)


if __name__ == "__main__":
    unittest.main()
