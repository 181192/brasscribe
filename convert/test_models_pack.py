"""models_pack.py against a pack served from a local folder: python3 -m unittest convert/test_models_pack.py

A stand-in `gh` on PATH answers `gh release download` by copying from that folder, so pack, fetch and
verify are tried end to end with no network and no real model.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models_pack  # noqa: E402

GH = """#!/bin/sh
# gh release download TAG --repo R --dir DIR --clobber --pattern P...
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir="$2"; shift ;;
    --pattern) cp "$FAKE_RELEASE/$2" "$dir/" || exit 1; shift ;;
  esac
  shift
done
"""


class ModelsPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.built, self.release, self.installed = t / "built", t / "release", t / "installed"
        package = self.built / "tone" / "tone-fp32.mlpackage"
        (package / "Data" / "weights").mkdir(parents=True)
        (package / "Manifest.json").write_text("{}")
        (package / "Data" / "weights" / "weight.bin").write_bytes(bytes(range(256)) * 40)
        (self.built / "tone" / "tone.onnx").write_bytes(b"onnx" * 1000)
        self.pin = t / "pin.json"
        self.pin.write_text(json.dumps({"version": "models-test", "repo": "nobody/nothing", "files": {
            "tone-fp32.mlpackage.zip": {"into": "tone"}, "tone.onnx": {"into": "tone"}}}))
        (t / "bin").mkdir()
        gh = t / "bin" / "gh"
        gh.write_text(GH)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.env = {"PATH": os.environ["PATH"], "FAKE_RELEASE": os.environ.get("FAKE_RELEASE")}
        os.environ["PATH"] = f"{t / 'bin'}{os.pathsep}{os.environ['PATH']}"
        os.environ["FAKE_RELEASE"] = str(self.release)
        self.real_pin, models_pack.PIN = models_pack.PIN, self.pin
        self.assertEqual(models_pack.pack(None, self.built, self.release), 0)

    def tearDown(self):
        models_pack.PIN = self.real_pin
        os.environ["PATH"] = self.env["PATH"]
        if self.env["FAKE_RELEASE"] is None:
            del os.environ["FAKE_RELEASE"]
        self.tmp.cleanup()

    def test_the_same_folder_packs_to_the_same_bytes(self):
        first = json.loads(self.pin.read_text())
        other = Path(self.tmp.name) / "again"
        self.assertEqual(models_pack.pack(None, self.built, other), 0)
        self.assertEqual(json.loads(self.pin.read_text()), first)
        self.assertEqual(models_pack.verify(self.built, []), 0)

    def test_fetch_installs_the_folder_and_the_file_and_keeps_them_next_time(self):
        self.assertEqual(models_pack.verify(self.installed, []), 1)
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        weights = self.installed / "tone" / "tone-fp32.mlpackage" / "Data" / "weights" / "weight.bin"
        self.assertEqual(weights.read_bytes(), bytes(range(256)) * 40)
        self.assertEqual((self.installed / "tone" / "tone.onnx").read_bytes(), b"onnx" * 1000)
        # nothing is downloaded again: the release can be gone
        os.environ["FAKE_RELEASE"] = str(self.release / "gone")
        self.assertEqual(models_pack.fetch(self.installed, []), 0)

    def test_a_changed_model_is_replaced_by_the_pinned_one(self):
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        weights = self.installed / "tone" / "tone-fp32.mlpackage" / "Data" / "weights" / "weight.bin"
        weights.write_bytes(b"other")
        self.assertEqual(models_pack.verify(self.installed, []), 1)
        self.assertEqual(models_pack.fetch(self.installed, ["tone-fp32.mlpackage.zip"]), 0)
        self.assertEqual(weights.read_bytes(), bytes(range(256)) * 40)

    def test_a_release_that_differs_from_the_pin_installs_nothing(self):
        (self.release / "tone.onnx").write_bytes(b"not the pinned file")
        with self.assertRaises(SystemExit):
            models_pack.fetch(self.installed, [])
        self.assertFalse(self.installed.exists())
        # and one whose checksum list was changed to agree with the file is refused by the pin itself
        sums = (self.release / "SHA256SUMS").read_text().splitlines()
        import hashlib
        fake = hashlib.sha256(b"not the pinned file").hexdigest()
        (self.release / "SHA256SUMS").write_text("\n".join(
            f"{fake}  tone.onnx" if line.endswith("tone.onnx") else line for line in sums) + "\n")
        with self.assertRaises(SystemExit):
            models_pack.fetch(self.installed, [])
        self.assertFalse(self.installed.exists())


if __name__ == "__main__":
    unittest.main()
