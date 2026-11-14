"""release-models.py on made-up artifacts: python3 .github/scripts/test_release_models.py

The pin here names the real files with made-up contents, so no model and no network is needed.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("release_models", Path(__file__).resolve().parent / "release-models.py")
release_models = importlib.util.module_from_spec(spec)
sys.modules["release_models"] = release_models
spec.loader.exec_module(release_models)

ONNX = {n: f"{n} weights".encode() * 50 for n in release_models.ANDROID}
APPLE_DIR = "Payload/BrasscribePlay.app/Models/"
MAC_DIR = "Brasscribe Play.app/Contents/Resources/Models/"
NOTICE = b"# On-device models: sources and licences (made up)\n"


def apk(extra: dict | None = None, drop: str = "") -> dict:
    files = {"classes.dex": b"dex", "lib/arm64-v8a/libonnxruntime.so": b"so", "assets/models/NOTICE.md": NOTICE}
    files |= {f"assets/models/{n}": d for n, d in ONNX.items() if n != drop}
    return files | (extra or {})


def apple(folder: str, compiled=("swift-f0-window-fp32", "nmp-b1-fp32", "beat-this-small0-fp16")) -> dict:
    files = {f"{folder}NOTICE.md": NOTICE}
    for c in compiled:
        files[f"{folder}{c}.mlmodelc/weights/weight.bin"] = b"w" * 100
        files[f"{folder}{c}.mlmodelc/model.mil"] = b"mil"
    return files


class ReleaseModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "dist"
        self.dir.mkdir()
        files = {n: {"into": "x", "sha256": hashlib.sha256(d).hexdigest(), "size": len(d)} for n, d in ONNX.items()}
        files |= {n: {"into": "x", "sha256": "0" * 64, "size": 1} for n in (*release_models.APPLE, "beat-this-small0-fp32.mlpackage.zip")}
        self.pin = Path(self.tmp.name) / "pin.json"
        self.pin.write_text(json.dumps({"version": "models-test", "repo": "nobody/nothing", "files": files}))
        self.notice = Path(self.tmp.name) / "NOTICE.md"
        self.notice.write_bytes(NOTICE)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, files: dict) -> Path:
        path = self.dir / name
        with zipfile.ZipFile(path, "w") as z:
            for n, d in files.items():
                z.writestr(n, d)
        return path

    def run_on(self, *paths: Path, require: tuple[str, ...] = ()) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        args = ["--pin", str(self.pin), "--notice", str(self.notice)] + [x for g in require for x in ("--require", g)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = release_models.main(args + [str(p) for p in paths])
        return code, out.getvalue(), err.getvalue()

    def test_a_full_release_folder_passes_and_lists_every_file(self):
        for abi in ("arm64-v8a", "universal"):
            self.write(f"brasscribe-play-android-{abi}.apk", apk())
            self.write(f"fretscribe-android-{abi}.apk", {"classes.dex": b"dex"})
        self.write("brasscribe-play-ios-unsigned.ipa", apple(APPLE_DIR))
        self.write("brasscribe-play-macos-arm64.zip", apple(MAC_DIR))
        self.write("fretscribe-ios-unsigned.ipa", {"Payload/Fretscribe.app/Info.plist": b"x"})
        self.write("fretscribe-macos-arm64.zip", {"Fretscribe.app/Contents/Info.plist": b"x"})
        self.write("brasscribe-play-windows-x64.zip", {"BrasscribePlay/BrasscribePlay.exe": b"x"})
        self.write("brasscribe-bandroom-macos-arm64.zip", {"Brasscribe Bandroom.app/Contents/Info.plist": b"x"})
        (self.dir / "SHA256SUMS").write_text("x  y\n")
        code, out, err = self.run_on(self.dir, require=("brasscribe-play-android-*.apk", "fretscribe-android-*.apk"))
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        rows = [line for line in out.splitlines() if line.startswith("| `")]
        self.assertEqual(len(rows), 11)  # every file, SHA256SUMS too
        self.assertIn("beat-this-small0.onnx (sha256", out)
        self.assertIn("beat-this-small0-fp16.mlmodelc (0.0 MB weights)", out)
        self.assertIn("| `brasscribe-play-windows-x64.zip` | Play for Windows | none | ok |", out)
        self.assertIn("| `SHA256SUMS` | | | not a zip archive, not checked |", out)
        self.assertIn("| `brasscribe-bandroom-macos-arm64.zip` | | none | no rule |", out)

    def test_an_apk_without_a_model_fails_naming_it(self):
        for name in ("brasscribe-play-android-arm64-v8a.apk", "brasscribe-arm64-v8a-release-unsigned.apk"):
            with self.subTest(name):
                code, out, err = self.run_on(self.write(name, apk(drop="nmp-b1.onnx")))
                self.assertEqual(code, 1)
                self.assertIn("no assets/models/nmp-b1.onnx", err)

    def test_an_apk_with_a_model_that_is_not_the_pinned_one_fails(self):
        changed = apk({"assets/models/swift-f0-window.onnx": b"other weights"})
        code, _, err = self.run_on(self.write("brasscribe-play-android-universal.apk", changed))
        self.assertEqual(code, 1)
        self.assertIn("assets/models/swift-f0-window.onnx is not the pinned file", err)

    def test_an_apk_with_an_empty_model_fails(self):
        code, _, err = self.run_on(self.write("brasscribe-play-android-universal.apk", apk({"assets/models/nmp-b1.onnx": b""})))
        self.assertEqual(code, 1)
        self.assertIn("nmp-b1.onnx is not the pinned file (0 bytes", err)

    def test_an_apk_with_an_extra_model_or_no_notice_fails(self):
        code, _, err = self.run_on(self.write("brasscribe-play-android-universal.apk", apk({"assets/models/old.onnx": b"x"})))
        self.assertEqual(code, 1)
        self.assertIn("assets/models/old.onnx should not be there", err)
        files = apk()
        del files["assets/models/NOTICE.md"]
        code, _, err = self.run_on(self.write("brasscribe-play-android-arm64-v8a.apk", files))
        self.assertEqual(code, 1)
        self.assertIn("no assets/models/NOTICE.md", err)

    def test_fretscribe_with_a_model_fails(self):
        code, _, err = self.run_on(self.write("fretscribe-android-arm64-v8a.apk", {"assets/models/nmp-b1.onnx": b"x"}))
        self.assertEqual(code, 1)
        self.assertIn("assets/models/nmp-b1.onnx should not be there", err)

    def test_a_file_named_as_an_apk_that_is_not_one_fails(self):
        path = self.dir / "brasscribe-play-android-arm64-v8a.apk"
        path.write_bytes(b"not a zip")
        code, out, _ = self.run_on(path)
        self.assertEqual(code, 1)
        self.assertIn("not a zip archive", out)

    def test_apple_rows_report_without_failing_until_enforced(self):
        ipa = self.write("brasscribe-play-ios-unsigned.ipa", apple(APPLE_DIR, compiled=("swift-f0-window-fp32", "beat-this-small0-fp32")))
        code, out, err = self.run_on(ipa)
        self.assertEqual(code, 0)
        self.assertIn("not enforced yet", out)
        self.assertIn("no Payload/BrasscribePlay.app/Models/nmp-b1-fp32.mlmodelc/weights/weight.bin", err)
        self.assertIn("beat-this-small0-fp32.mlmodelc should not be there", err)
        enforced = tuple(r if r.pattern != "brasscribe-play-ios*.ipa" else release_models.Rule(**{**r.__dict__, "enforced": True})
                         for r in release_models.RULES)
        real, release_models.RULES = release_models.RULES, enforced
        try:
            self.assertEqual(self.run_on(ipa)[0], 1)
        finally:
            release_models.RULES = real

    def test_every_pinned_name_in_the_rules_is_in_the_real_pin(self):
        pinned = set(json.loads(release_models.PIN.read_text())["files"])
        self.assertLessEqual({n for r in release_models.RULES for n in r.onnx + r.coreml}, pinned)


    def test_a_notice_that_is_not_the_models_notice_fails(self):
        code, _, err = self.run_on(self.write("brasscribe-play-android-universal.apk", apk({"assets/models/NOTICE.md": b"other"})))
        self.assertEqual(code, 1)
        self.assertIn("assets/models/NOTICE.md is not convert/on-device-models-NOTICE.md", err)

    def test_a_required_file_that_is_not_there_fails(self):
        self.write("fretscribe-android-arm64-v8a.apk", {"classes.dex": b"dex"})
        code, out, err = self.run_on(self.dir, require=("brasscribe-play-android-*.apk",))
        self.assertEqual(code, 1)
        self.assertIn("no file matches brasscribe-play-android-*.apk", err)
        self.assertIn("**wrong**: no such file", out)
        # an empty folder too
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(self.run_on(empty, require=("brasscribe-play-android-*.apk",))[0], 1)

    def test_an_app_package_with_no_rule_fails(self):
        for name in ("app-arm64-v8a-release-unsigned.apk", "SomethingElse.ipa"):
            with self.subTest(name):
                code, out, err = self.run_on(self.write(name, apk()))
                self.assertEqual(code, 1)
                self.assertIn("no rule for this app package", out)

    def test_a_report_only_file_that_is_not_a_zip_still_gets_a_row(self):
        path = self.dir / "brasscribe-play-ios-unsigned.ipa"
        path.write_bytes(b"not a zip")
        code, out, _ = self.run_on(path)
        self.assertEqual(code, 0)
        self.assertIn("| `brasscribe-play-ios-unsigned.ipa` | Play for iPhone and iPad | | not a zip archive, not checked |", out)

    def test_windows_with_a_model_fails(self):
        code, _, err = self.run_on(self.write("brasscribe-play-windows-x64.zip", {"BrasscribePlay/Models/swift-f0-stream.onnx": b"x"}))
        self.assertEqual(code, 1)
        self.assertIn("swift-f0-stream.onnx should not be there", err)

    def test_the_real_notice_is_the_default(self):
        self.assertEqual(release_models.NOTICE, release_models.PIN.parent / "on-device-models-NOTICE.md")
        self.assertTrue(release_models.NOTICE.is_file())


if __name__ == "__main__":
    unittest.main()
