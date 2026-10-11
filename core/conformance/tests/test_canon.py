"""The exact comparisons the conformance runner relies on.

    uv run python -m unittest discover -s tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scribe_conformance.canon import json_equal, same_json
from scribe_conformance.run import compare


class SameJson(unittest.TestCase):
    def test_equal_values(self):
        self.assertTrue(same_json({"a": [1, 2.5, None, "x", True], "b": {"c": -0.0}},
                                  {"a": [1, 2.5, None, "x", True], "b": {"c": -0.0}}))

    def test_int_is_not_float(self):
        self.assertFalse(same_json(1, 1.0))
        self.assertFalse(same_json([0], [0.0]))

    def test_bool_is_not_int(self):
        self.assertFalse(same_json(True, 1))
        self.assertFalse(same_json(0, False))

    def test_negative_zero_is_not_zero(self):
        self.assertFalse(same_json(-0.0, 0.0))
        self.assertFalse(same_json({"x": 0.0}, {"x": -0.0}))

    def test_floats_bit_for_bit(self):
        self.assertTrue(same_json(0.1 + 0.2, 0.30000000000000004))
        self.assertFalse(same_json(0.1 + 0.2, 0.3))

    def test_key_order(self):
        self.assertFalse(same_json({"a": 1, "b": 2}, {"b": 2, "a": 1}))

    def test_list_length(self):
        self.assertFalse(same_json([1, 2], [1, 2, 3]))


class JsonFiles(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text)
        return p

    def test_detail_names_the_first_difference(self):
        a = self.write("a.json", '{"notes": [{"start": 0, "vel": 1.0}]}')
        b = self.write("b.json", '{"notes": [{"start": 0, "vel": 1}]}')
        same, byte_same, detail = json_equal(a, b)
        self.assertFalse(same)
        self.assertFalse(byte_same)
        self.assertIn("$.notes[0].vel", detail)

    def test_float_detail_shows_the_bits(self):
        a = self.write("a.json", '[-0.0]')
        b = self.write("b.json", '[0.0]')
        _, _, detail = json_equal(a, b)
        self.assertIn("-0x0.0p+0", detail)

    def test_compare_fails_on_bytes(self):
        for d in ("ref", "rs"):
            (self.dir / d).mkdir()
        (self.dir / "ref" / "x.json").write_text('{"a": 1}')
        (self.dir / "rs" / "x.json").write_text('{"a":1}')
        [(name, ok, detail)] = compare(self.dir / "ref", self.dir / "rs", ["x.json"])
        self.assertEqual(name, "x.json")
        self.assertFalse(ok)
        self.assertIn("bytes differ", detail)

    def test_compare_passes_identical_files(self):
        for d in ("ref", "rs"):
            (self.dir / d).mkdir()
            (self.dir / d / "x.json").write_text('{"a": 1.5}')
        [(_, ok, detail)] = compare(self.dir / "ref", self.dir / "rs", ["x.json"])
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
