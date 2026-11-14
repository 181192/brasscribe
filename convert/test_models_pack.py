"""models_pack.py against a pack served from a local folder: python3 -m unittest convert/test_models_pack.py

A stand-in `gh` on PATH answers `gh release download` by copying from that folder, so pack, fetch and
verify are tried end to end with no network and no real model.
"""

import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models_pack  # noqa: E402

GH = """#!/bin/sh
# gh release download TAG --repo R --dir DIR --clobber --pattern P...
# FAKE_FAILS: a file holding how many of the next calls fail; FAKE_SLOW: seconds every call takes.
if [ -n "$FAKE_FAILS" ] && [ -s "$FAKE_FAILS" ]; then
  n=$(cat "$FAKE_FAILS")
  if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$FAKE_FAILS"; echo "HTTP 502" >&2; exit 1; fi
fi
[ -n "$FAKE_SLOW" ] && sleep "$FAKE_SLOW"
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
        self.env = {k: os.environ.get(k) for k in ("PATH", "FAKE_RELEASE", "FAKE_FAILS", "FAKE_SLOW")}
        self.real_timeout = models_pack.GH_TIMEOUT
        os.environ["PATH"] = f"{t / 'bin'}{os.pathsep}{os.environ['PATH']}"
        os.environ["FAKE_RELEASE"] = str(self.release)
        self.real_pin, models_pack.PIN = models_pack.PIN, self.pin
        self.assertEqual(models_pack.pack(None, self.built, self.release), 0)

    def tearDown(self):
        models_pack.PIN = self.real_pin
        models_pack.GH_TIMEOUT = self.real_timeout
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def fails(self, n: int) -> Path:
        """The next n downloads fail."""
        counter = Path(self.tmp.name) / "fails"
        counter.write_text(str(n))
        os.environ["FAKE_FAILS"] = str(counter)
        return counter

    def republish(self, name: str, data: bytes) -> None:
        """A release whose file `name` is `data`, with SHA256SUMS and the pin agreeing with it."""
        (self.release / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        sums = (self.release / "SHA256SUMS").read_text().splitlines()
        (self.release / "SHA256SUMS").write_text("\n".join(
            f"{digest}  {name}" if line.endswith(f"  {name}") else line for line in sums) + "\n")
        pin = json.loads(self.pin.read_text())
        pin["files"][name].update(sha256=digest, size=len(data))
        self.pin.write_text(json.dumps(pin))

    def installed_files(self) -> list[str]:
        return sorted(p.relative_to(self.installed).as_posix() for p in self.installed.rglob("*")) \
            if self.installed.exists() else []

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


    def test_a_failed_download_is_tried_once_more(self):
        counter = self.fails(1)
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        self.assertEqual(counter.read_text().strip(), "0")

    def test_a_download_that_fails_twice_installs_nothing(self):
        self.fails(2)
        with self.assertRaises(SystemExit):
            models_pack.fetch(self.installed, [])
        self.assertEqual(self.installed_files(), [])

    def test_a_stalled_download_is_given_up_after_the_timeout(self):
        models_pack.GH_TIMEOUT = 0.3
        os.environ["FAKE_SLOW"] = "3"
        with self.assertRaises(SystemExit):
            models_pack.fetch(self.installed, [])
        self.assertEqual(self.installed_files(), [])

    def test_a_truncated_download_installs_nothing_and_keeps_what_was_there(self):
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        (self.installed / "tone" / "tone.onnx").write_bytes(b"older")
        before = self.installed_files()
        whole = (self.release / "tone.onnx").read_bytes()
        (self.release / "tone.onnx").write_bytes(whole[: len(whole) // 2])
        with self.assertRaises(SystemExit):
            models_pack.fetch(self.installed, [])
        self.assertEqual((self.installed / "tone" / "tone.onnx").read_bytes(), b"older")
        self.assertEqual(self.installed_files(), before)

    def test_an_unknown_file_name_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            models_pack.fetch(self.installed, ["tone.onnx", "nothing.onnx"])
        self.assertIn("nothing.onnx", str(e.exception))
        with self.assertRaises(SystemExit):
            models_pack.verify(self.installed, ["nothing.onnx"])
        self.assertEqual(self.installed_files(), [])

    def test_an_extra_file_in_an_installed_package_is_found_and_removed(self):
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        package = self.installed / "tone" / "tone-fp32.mlpackage"
        (package / "Data" / "stray.bin").write_bytes(b"stray")
        self.assertEqual(models_pack.verify(self.installed, ["tone-fp32.mlpackage.zip"]), 1)
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        self.assertFalse((package / "Data" / "stray.bin").exists())
        # nothing is left beside it from the swap
        self.assertEqual(sorted(p.name for p in (self.installed / "tone").iterdir()), ["tone-fp32.mlpackage", "tone.onnx"])

    def test_a_zip_entry_outside_its_folder_installs_nothing(self):
        for outside in ("elsewhere/evil.bin", "tone-fp32.mlpackage/../evil.bin"):
            with self.subTest(outside):
                out = io.BytesIO()
                with zipfile.ZipFile(out, "w") as z:
                    z.writestr("tone-fp32.mlpackage/Manifest.json", "{}")
                    z.writestr(outside, "evil")
                self.republish("tone-fp32.mlpackage.zip", out.getvalue())
                with self.assertRaises(SystemExit) as e:
                    models_pack.fetch(self.installed, ["tone-fp32.mlpackage.zip"])
                self.assertIn("outside", str(e.exception))
                self.assertFalse((self.installed / "tone" / "tone-fp32.mlpackage").exists())
                self.assertFalse(any(p.name == "evil.bin" for p in Path(self.tmp.name).rglob("*")))


    def test_an_installed_file_has_the_mode_a_plain_write_gives(self):
        old = os.umask(0o022)
        try:
            self.assertEqual(models_pack.fetch(self.installed, []), 0)
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE((self.installed / "tone" / "tone.onnx").stat().st_mode), 0o644)

    def test_what_a_killed_install_left_behind_is_cleaned_up(self):
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        tone = self.installed / "tone"
        (tone / ".tone.onnx.abc123").write_bytes(b"half")
        (tone / ".tone-fp32.mlpackage.def456" / "tone-fp32.mlpackage").mkdir(parents=True)
        (tone / "other.bin").write_bytes(b"not ours")
        self.assertEqual(models_pack.fetch(self.installed, []), 0)
        self.assertEqual(sorted(p.name for p in tone.iterdir()), ["other.bin", "tone-fp32.mlpackage", "tone.onnx"])


if __name__ == "__main__":
    unittest.main()
