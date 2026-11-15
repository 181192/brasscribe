"""check-aab.py on made-up bundles: python3 .github/scripts/test_check_aab.py

The bundles are built here from a small manifest (aapt2 writes it in the protobuf format a bundle carries) and
signed with throwaway keys made for the run, so no release key and no app build is needed. Needs a JDK (keytool,
jarsigner) and the Android SDK's build tools and a platform (ANDROID_HOME).
"""

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_aab", Path(__file__).resolve().parent / "check-aab.py")
check_aab = importlib.util.module_from_spec(spec)
sys.modules["check_aab"] = check_aab
spec.loader.exec_module(check_aab)

SDK = Path(os.environ.get("ANDROID_HOME") or "/opt/homebrew/share/android-commandlinetools")
PASSWORD = "throwaway"
PERMISSIONS = ("android.permission.RECORD_AUDIO", "android.permission.INTERNET")


def manifest_xml(package="app.example.tune", code="7", name="1.2.3", debuggable=False, permissions=PERMISSIONS) -> str:
    perms = "".join(f'<uses-permission android:name="{p}"/>' for p in permissions)
    return (f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}" '
            f'android:versionCode="{code}" android:versionName="{name}">'
            f'<uses-sdk android:minSdkVersion="36" android:targetSdkVersion="37"/>{perms}'
            f'<application android:label="Tune" android:debuggable="{str(debuggable).lower()}"/></manifest>')


class CheckAab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.aapt2 = check_aab.aapt2()
        platforms = sorted((SDK / "platforms").glob("android-*/android.jar"))
        if not platforms:
            raise SystemExit(f"test_check_aab: no Android platform under {SDK}/platforms")
        cls.android_jar = str(platforms[-1])
        cls.keys = {}
        for alias in ("release", "other"):
            ks = cls.tmp / f"{alias}.jks"
            subprocess.run([check_aab.java_tool("keytool"), "-genkeypair", "-keystore", str(ks), "-storepass", PASSWORD,
                            "-alias", alias, "-keyalg", "RSA", "-keysize", "2048", "-dname", f"CN={alias}",
                            "-validity", "2", "-noprompt"], check=True, capture_output=True)
            out = subprocess.run([check_aab.java_tool("keytool"), "-list", "-v", "-keystore", str(ks), "-storepass",
                                  PASSWORD, "-alias", alias], check=True, capture_output=True, text=True).stdout
            sha = next(line.split(":", 1)[1].strip() for line in out.splitlines() if line.strip().startswith("SHA256:"))
            cls.keys[alias] = (ks, sha)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["rm", "-rf", str(cls.tmp)], check=False)

    def link(self, xml: str, proto: bool) -> Path:
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        (d / "AndroidManifest.xml").write_text(xml)
        out = d / "linked.zip"
        subprocess.run([self.aapt2, "link", *(["--proto-format"] if proto else []), "-o", str(out), "--manifest",
                        str(d / "AndroidManifest.xml"), "-I", self.android_jar], check=True, capture_output=True)
        return out

    def bundle(self, *signers: str, **manifest) -> Path:
        linked = self.link(manifest_xml(**manifest), proto=True)
        aab = linked.with_name("app.aab")
        with zipfile.ZipFile(linked) as src, zipfile.ZipFile(aab, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("BundleConfig.pb", b"")
            z.writestr("base/manifest/AndroidManifest.xml", src.read("AndroidManifest.xml"))
            z.writestr("base/resources.pb", src.read("resources.pb"))
            z.writestr("base/dex/classes.dex", b"dex")
        for alias in signers:
            subprocess.run([check_aab.java_tool("jarsigner"), "-keystore", str(self.keys[alias][0]), "-storepass:env",
                            "AAB_TEST_PASSWORD", str(aab), alias], check=True, capture_output=True,
                           env={**os.environ, "AAB_TEST_PASSWORD": PASSWORD})
        return aab

    def apk(self, **manifest) -> Path:
        return self.link(manifest_xml(**manifest), proto=False)

    def run_check(self, aab: Path, *extra: str, cert: str | None = None) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = check_aab.main([str(aab), "--cert", cert or self.keys["release"][1], "--package", "app.example.tune", *extra])
        return code, err.getvalue()

    def test_reads_the_protobuf_manifest(self):
        f = check_aab.facts(check_aab.manifest(self.bundle()))
        self.assertEqual((f.package, f.version_name, f.version_code, f.min_sdk, f.target_sdk, f.debuggable),
                         ("app.example.tune", "1.2.3", "7", "36", "37", False))
        self.assertEqual(f.permissions, sorted(PERMISSIONS))

    def test_a_bundle_signed_with_the_release_key_passes(self):
        code, err = self.run_check(self.bundle("release"), "--version-name", "1.2.3", "--version-code", "7")
        self.assertEqual(code, 0, err)

    def test_the_certificate_matches_without_colons_and_in_any_case(self):
        code, err = self.run_check(self.bundle("release"), cert=self.keys["release"][1].replace(":", "").lower())
        self.assertEqual(code, 0, err)

    def test_an_unsigned_bundle_is_refused(self):
        code, err = self.run_check(self.bundle())
        self.assertEqual(code, 1)
        self.assertIn("is not signed", err)

    def test_a_bundle_signed_with_another_key_is_refused(self):
        code, err = self.run_check(self.bundle("other"))
        self.assertEqual(code, 1)
        self.assertIn("is signed with certificate", err)

    def test_a_bundle_with_a_second_signer_is_refused(self):
        code, err = self.run_check(self.bundle("release", "other"))
        self.assertEqual(code, 1)
        self.assertIn("2 signers", err)

    def test_a_bundle_changed_after_signing_is_refused(self):
        aab = self.bundle("release")
        changed = aab.with_name("changed.aab")
        with zipfile.ZipFile(aab) as src, zipfile.ZipFile(changed, "w") as z:
            for info in src.infolist():
                data = src.read(info.filename)
                z.writestr(info, data + b"!" if info.filename == "base/dex/classes.dex" else data)
        code, err = self.run_check(changed)
        self.assertEqual(code, 1)
        self.assertIn("does not verify", err)

    def test_an_entry_added_after_signing_is_refused(self):
        aab = self.bundle("release")
        with zipfile.ZipFile(aab, "a") as z:
            z.writestr("base/assets/extra.bin", b"extra")
        code, err = self.run_check(aab)
        self.assertEqual(code, 1)
        self.assertIn("no signature covers", err)

    def test_another_package_is_refused(self):
        code, err = self.run_check(self.bundle("release", package="app.example.other"))
        self.assertEqual(code, 1)
        self.assertIn("is app.example.other, not app.example.tune", err)

    def test_a_debuggable_bundle_is_refused(self):
        code, err = self.run_check(self.bundle("release", debuggable=True))
        self.assertEqual(code, 1)
        self.assertIn("debuggable", err)

    def test_another_version_is_refused(self):
        aab = self.bundle("release")
        self.assertIn("versionName", self.run_check(aab, "--version-name", "1.2.4")[1])
        self.assertIn("versionCode", self.run_check(aab, "--version-code", "8")[1])

    def test_like_an_apk_of_the_same_build_passes(self):
        code, err = self.run_check(self.bundle("release"), "--like", str(self.apk()))
        self.assertEqual(code, 0, err)

    def test_like_an_apk_with_other_permissions_or_version_is_refused(self):
        aab = self.bundle("release")
        code, err = self.run_check(aab, "--like", str(self.apk(permissions=PERMISSIONS[:1])))
        self.assertEqual(code, 1)
        self.assertIn("only in the bundle: android.permission.INTERNET", err)
        code, err = self.run_check(aab, "--like", str(self.apk(code="8")))
        self.assertEqual(code, 1)
        self.assertIn("versionCode", err)

    def test_print_shows_one_value_of_an_unsigned_bundle(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_aab.main(["--print", "package", str(self.bundle())])
        self.assertEqual((code, out.getvalue()), (0, "app.example.tune\n"))

    def test_without_a_certificate_nothing_is_checked(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            check_aab.main(["--package", "app.example.tune", str(self.bundle("release"))])

    def test_a_zip_that_is_not_a_bundle_is_refused(self):
        code, err = self.run_check(self.apk())
        self.assertEqual(code, 1)
        self.assertIn("not an app bundle", err)


if __name__ == "__main__":
    unittest.main()
