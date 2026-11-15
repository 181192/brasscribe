"""scripts/play-upload.sh against a stand-in curl: python3 scripts/test_play_upload.py

No network and no real key: a curl on PATH answers as Google would (or fails where a test says) and logs every call,
the service account's key is made for the run, and the bundle is a made-up one with the protobuf manifest aapt2
writes (needs the Android SDK's build tools and a platform, ANDROID_HOME). The release notes come from
.github/scripts/play-notes.py, tested here too.
"""

import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "play-upload.sh"
SDK = Path(os.environ.get("ANDROID_HOME") or "/opt/homebrew/share/android-commandlinetools")

spec = importlib.util.spec_from_file_location("play_notes", ROOT / ".github" / "scripts" / "play-notes.py")
play_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play_notes)

# The stand-in: logs each call as one JSON line, then answers by the step the URL is for.
FAKE_CURL = r'''#!/usr/bin/env python3
import hashlib, json, os, sys
args, i = sys.argv[1:], 0
call = {"method": "GET", "url": "", "headers": [], "auth": "", "form": [], "body_sha256": "", "body": ""}
write_out = ""
while i < len(args):
    a = args[i]
    if a in ("-sS", "-s", "-S"): pass
    elif a == "-X": i += 1; call["method"] = args[i]
    elif a == "-H": i += 1; call["headers"].append(args[i])
    elif a == "-K":
        i += 1
        for line in open(args[i]):
            if line.startswith("header"): call["auth"] = line.split('"')[1]
    elif a == "-w": i += 1; write_out = args[i]
    elif a == "--data-binary":
        i += 1; data = sys.stdin.buffer.read() if args[i] == "@-" else args[i].encode()
        call["body"] = data.decode(errors="replace")
    elif a == "--upload-file":
        i += 1; data = open(args[i], "rb").read(); call["body_sha256"] = hashlib.sha256(data).hexdigest()
    elif a == "--data-urlencode":
        i += 1; v = args[i]
        if v.endswith("@-"): v = v[:-2] + "=" + sys.stdin.read()
        call["form"].append(v)
    elif a.startswith("-"): sys.exit(f"stand-in curl: unknown option {a}")
    else: call["url"] = a
    i += 1
url, m = call["url"], call["method"]
step = ("token" if url.endswith("/token") else "delete" if m == "DELETE" else "commit" if url.endswith(":commit")
        else "upload" if "/bundles" in url else "track" if "/tracks/" in url else "edit" if url.endswith("/edits") else "?")
call["step"] = step
with open(os.environ["FAKE_LOG"], "a") as log: log.write(json.dumps(call) + "\n")
if step == os.environ.get("FAKE_FAIL"):
    body, status = '{"error": {"code": 403, "message": "The caller does not have permission"}}', 403
else:
    body, status = {"token": '{"access_token": "ya29.stand-in-token", "expires_in": 3599}', "edit": '{"id": "edit-42"}',
                    "upload": json.dumps({"versionCode": int(os.environ.get("FAKE_CODE", "7"))}),
                    "track": "{}", "commit": "{}", "delete": ""}.get(step, "{}"), 200
sys.stdout.write(body + (write_out.replace("\\n", "\n").replace("%{http_code}", str(status)) if write_out else ""))
'''


class PlayUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        bin_ = cls.tmp / "bin"
        bin_.mkdir()
        (bin_ / "curl").write_text(FAKE_CURL)
        (bin_ / "curl").chmod(0o755)
        cls.path = f"{bin_}{os.pathsep}{os.environ['PATH']}"
        # A throwaway service account key, made for this run only.
        pem = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                             check=True, capture_output=True, text=True).stdout
        cls.public = subprocess.run(["openssl", "pkey", "-pubout"], input=pem, check=True, capture_output=True,
                                    text=True).stdout
        cls.account = json.dumps({"type": "service_account", "client_email": "uploader@example.iam.gserviceaccount.com",
                                  "private_key": pem, "token_uri": "https://oauth2.example.com/token"})
        cls.pem = pem
        cls.aab = cls.bundle(cls.tmp)
        cls.en = cls.tmp / "notes-en.txt"
        cls.nb = cls.tmp / "notes-nb.txt"
        cls.en.write_text("• The answers in dialogs are 48 dp tall\n")
        cls.nb.write_text("Nytt i denne versjonen (på engelsk):\n• The answers in dialogs are 48 dp tall\n")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["rm", "-rf", str(cls.tmp)], check=False)

    @staticmethod
    def bundle(tmp: Path) -> Path:
        aapt2 = sorted((SDK / "build-tools").glob("*/aapt2"))[-1]
        android_jar = sorted((SDK / "platforms").glob("android-*/android.jar"))[-1]
        (tmp / "AndroidManifest.xml").write_text(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="app.example.tune" '
            'android:versionCode="7" android:versionName="1.2.3"><application/></manifest>')
        linked = tmp / "linked.zip"
        subprocess.run([str(aapt2), "link", "--proto-format", "-o", str(linked), "--manifest",
                        str(tmp / "AndroidManifest.xml"), "-I", str(android_jar)], check=True, capture_output=True)
        aab = tmp / "tune.aab"
        with zipfile.ZipFile(linked) as src, zipfile.ZipFile(aab, "w") as z:
            z.writestr("BundleConfig.pb", b"")
            z.writestr("base/manifest/AndroidManifest.xml", src.read("AndroidManifest.xml"))
            z.writestr("base/dex/classes.dex", b"dex")
        return aab

    def run_upload(self, *args: str, fail: str = "", code: str = "7", account: str | None = None):
        log = Path(tempfile.mkstemp(dir=self.tmp)[1])
        work = Path(tempfile.mkdtemp(dir=self.tmp))
        env = {**os.environ, "PATH": self.path, "FAKE_LOG": str(log), "FAKE_FAIL": fail, "FAKE_CODE": code,
               "PLAY_SERVICE_ACCOUNT_JSON": self.account if account is None else account, "TMPDIR": str(work)}
        env.pop("GITHUB_ACTIONS", None)
        argv = list(args) or ["--track", "internal", "--notes-en", str(self.en), "--notes-nb", str(self.nb), str(self.aab)]
        r = subprocess.run(["bash", str(SCRIPT), *argv], env=env, capture_output=True, text=True, cwd=work)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return r, calls, work

    def test_the_whole_flow_in_order(self):
        r, calls, _ = self.run_upload()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["step"] for c in calls], ["token", "edit", "upload", "track", "commit"])
        base = "https://androidpublisher.googleapis.com/"
        self.assertEqual(calls[1]["url"], base + "androidpublisher/v3/applications/app.example.tune/edits")
        self.assertEqual(calls[2]["url"], base + "upload/androidpublisher/v3/applications/app.example.tune/edits/edit-42/bundles?uploadType=media")
        self.assertEqual(calls[3]["method"], "PUT")
        self.assertTrue(calls[3]["url"].endswith("/edits/edit-42/tracks/internal"))
        self.assertTrue(calls[4]["url"].endswith("/edits/edit-42:commit"))
        for c in calls[1:]:
            self.assertEqual(c["auth"], "Authorization: Bearer ya29.stand-in-token")
        self.assertIn("internal testing track", r.stdout)

    def test_the_bundle_is_uploaded_as_it_is(self):
        import hashlib
        _, calls, _ = self.run_upload()
        self.assertEqual(calls[2]["body_sha256"], hashlib.sha256(self.aab.read_bytes()).hexdigest())
        self.assertIn("Content-Type: application/octet-stream", calls[2]["headers"])

    def test_the_track_gets_a_completed_release_with_both_languages(self):
        _, calls, _ = self.run_upload()
        body = json.loads(calls[3]["body"])
        self.assertEqual(body["track"], "internal")
        (release,) = body["releases"]
        self.assertEqual((release["versionCodes"], release["status"]), (["7"], "completed"))
        notes = {n["language"]: n["text"] for n in release["releaseNotes"]}
        self.assertEqual(notes["en-US"], "• The answers in dialogs are 48 dp tall")
        self.assertTrue(notes["no-NO"].startswith("Nytt i denne versjonen"))

    def test_the_token_request_is_a_valid_rs256_jwt_with_a_short_life(self):
        _, calls, work = self.run_upload()
        form = dict(f.split("=", 1) for f in calls[0]["form"])
        self.assertEqual(form["grant_type"], "urn:ietf:params:oauth:grant-type:jwt-bearer")
        header, claims, signature = form["assertion"].split(".")
        pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        self.assertEqual(json.loads(pad(header)), {"alg": "RS256", "typ": "JWT"})
        c = json.loads(pad(claims))
        self.assertEqual(c["scope"], "https://www.googleapis.com/auth/androidpublisher")
        self.assertEqual((c["iss"], c["aud"]), ("uploader@example.iam.gserviceaccount.com", "https://oauth2.example.com/token"))
        self.assertLessEqual(c["exp"] - c["iat"], 3600)
        pub, sig = work / "pub.pem", work / "sig.bin"
        pub.write_text(self.public)
        sig.write_bytes(pad(signature))
        v = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)],
                           input=f"{header}.{claims}".encode(), capture_output=True)
        self.assertEqual(v.returncode, 0, v.stderr)

    def test_the_key_is_never_written_or_printed(self):
        r, calls, work = self.run_upload()
        body = self.pem.split("\n")[1]
        self.assertNotIn(body, r.stdout + r.stderr)
        self.assertNotIn(body, json.dumps(calls))
        self.assertEqual(list(work.iterdir()), [])  # nothing left in its working folder or its TMPDIR

    def test_a_failure_after_the_edit_is_open_deletes_the_edit(self):
        for step in ("upload", "track", "commit"):
            with self.subTest(step):
                r, calls, _ = self.run_upload(fail=step)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(calls[-1]["step"], "delete")
                self.assertTrue(calls[-1]["url"].endswith("/edits/edit-42"))
                self.assertIn("403", r.stderr)
                self.assertIn("the edit was deleted", r.stderr)

    def test_a_refused_token_or_edit_stops_without_anything_to_delete(self):
        for step, steps in (("token", ["token"]), ("edit", ["token", "edit"])):
            with self.subTest(step):
                r, calls, _ = self.run_upload(fail=step)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual([c["step"] for c in calls], steps)

    def test_play_reading_another_version_code_deletes_the_edit(self):
        r, calls, _ = self.run_upload(code="8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("version code 8", r.stderr)
        self.assertEqual([c["step"] for c in calls], ["token", "edit", "upload", "delete"])

    def test_only_the_internal_track(self):
        for track in ("production", "beta", "alpha", ""):
            with self.subTest(track):
                r, calls, _ = self.run_upload("--track", track, "--notes-en", str(self.en), "--notes-nb", str(self.nb), str(self.aab))
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(calls, [])

    def test_a_dry_run_calls_nothing(self):
        r, calls, _ = self.run_upload("--dry-run", "--track", "internal", "--notes-en", str(self.en), "--notes-nb", str(self.nb), str(self.aab))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, [])
        self.assertIn("app.example.tune, version code 7", r.stdout)

    def test_notes_too_long_or_a_bad_key_stop_before_any_call(self):
        long = self.tmp / "long.txt"
        long.write_text("x" * 501)
        r, calls, _ = self.run_upload("--track", "internal", "--notes-en", str(long), "--notes-nb", str(self.nb), str(self.aab))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(calls, [])
        for account in ("", "not json", json.dumps({"client_email": "x@example.com", "private_key": "nope"})):
            with self.subTest(account=account[:10]):
                r, calls, _ = self.run_upload(account=account)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(calls, [])

    def test_in_actions_the_token_and_the_jwt_are_masked(self):
        log = Path(tempfile.mkstemp(dir=self.tmp)[1])
        env = {**os.environ, "PATH": self.path, "FAKE_LOG": str(log), "PLAY_SERVICE_ACCOUNT_JSON": self.account,
               "GITHUB_ACTIONS": "true"}
        r = subprocess.run(["bash", str(SCRIPT), "--track", "internal", "--notes-en", str(self.en), "--notes-nb",
                            str(self.nb), str(self.aab)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("::add-mask::ya29.stand-in-token", r.stdout)
        self.assertEqual(r.stdout.count("::add-mask::"), 2)


CHANGELOG = """# Changelog

## 1.3.0 (2026-12-01)

### New features

- **Android:** The tuner shows the [nearest note](https://example.com) ([#601](https://github.com/x/y/pull/601))
- **Android:** Fretscribe shows the capo on the tab ([#602](https://github.com/x/y/pull/602))
- **Site:** A new page ([#603](https://github.com/x/y/pull/603))
- Every app opens its licences from About ([#604](https://github.com/x/y/pull/604))

### Fixes

- **Android:** The band plays after a call ([#605](https://github.com/x/y/pull/605))

### Under the hood

- **Android:** A faster build ([#606](https://github.com/x/y/pull/606))

## 1.2.0 (2026-11-01)

### Fixes

- **Android:** Older fix ([#500](https://github.com/x/y/pull/500))
"""


class PlayNotes(unittest.TestCase):
    def test_the_apps_own_android_items_without_links(self):
        self.assertEqual(play_notes.notes(CHANGELOG, "1.3.0", "brasscribe", "en-US"),
                         "• The tuner shows the nearest note\n• Every app opens its licences from About\n"
                         "• The band plays after a call")
        self.assertEqual(play_notes.notes(CHANGELOG, "1.3.0", "fretscribe", "en-US"),
                         "• The tuner shows the nearest note\n• Fretscribe shows the capo on the tab\n"
                         "• Every app opens its licences from About")

    def test_nb_no_says_the_notes_are_in_english(self):
        self.assertTrue(play_notes.notes(CHANGELOG, "1.3.0", "brasscribe", "no-NO").startswith("Nytt i denne versjonen (på engelsk):\n• "))

    def test_at_most_500_characters(self):
        many = "## 2.0.0\n\n### Fixes\n\n" + "".join(f"- **Android:** Fix number {i} of many words here\n" for i in range(40))
        for lang in ("en-US", "no-NO"):
            text = play_notes.notes(many, "2.0.0", "brasscribe", lang)
            self.assertLessEqual(len(text), 500)
            self.assertTrue(text.endswith("…"))

    def test_a_version_with_nothing_for_the_app_gets_a_plain_line_and_an_unknown_one_fails(self):
        self.assertEqual(play_notes.notes("## 3.0.0\n\n### Fixes\n\n- **Site:** x\n", "3.0.0", "brasscribe", "no-NO"),
                         "Små forbedringer og rettelser.")
        with self.assertRaises(SystemExit):
            play_notes.notes(CHANGELOG, "9.9.9", "brasscribe", "en-US")


if __name__ == "__main__":
    unittest.main()
