"""prune-caches.py on made-up cache lists: python3 .github/scripts/test_prune_caches.py"""

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("prune_caches", Path(__file__).resolve().parent / "prune-caches.py")
prune = importlib.util.module_from_spec(spec)
sys.modules["prune_caches"] = prune
spec.loader.exec_module(prune)

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
H1, H2 = "09f0b55bedf5050941e7969ebd50e59e", "ae397b3ed8e55989b600d66c65923063"


def cache(key: str, ref: str = prune.MAIN, created: str = "2026-11-15T10:00:00Z", accessed: str = "") -> dict:
    return {"key": key, "ref": ref, "created_at": created, "last_accessed_at": accessed or created, "size_in_bytes": 1}


def keys(caches: list[dict]) -> list[str]:
    return sorted(c["key"] for c in prune.stale(caches, NOW))


class Family(unittest.TestCase):
    def test_hashes_are_taken_out(self):
        self.assertEqual(prune.family(f"gradle-Linux-android-tests-{H1}"), "gradle-Linux-android-tests-*")
        self.assertEqual(prune.family("v0-rust-core-Linux-x64-2fd77104-31d35653"), "v0-rust-core-Linux-x64-*-*")

    def test_what_follows_a_hash_stays(self):
        self.assertNotEqual(prune.family(f"band-sounds-Windows-{H1}-brass.sf2"), prune.family(f"band-sounds-Windows-{H1}-mobile.sf2"))

    def test_words_and_versions_are_not_hashes(self):
        self.assertEqual(prune.family("verovio-macOS-ARM64-xcode26.6-all-abc"), "verovio-macOS-ARM64-xcode26.6-all-abc")


class Stale(unittest.TestCase):
    def test_older_generation_on_main_goes(self):
        old = cache(f"gradle-Linux-android-tests-{H2}", created="2026-11-14T10:00:00Z", accessed="2026-11-15T11:00:00Z")
        new = cache(f"gradle-Linux-android-tests-{H1}")
        self.assertEqual(keys([old, new]), [old["key"]])

    def test_different_caches_on_main_stay(self):
        self.assertEqual(keys([cache(f"gradle-Linux-android-tests-{H1}"), cache(f"verovio-macOS-ARM64-{H2}")]), [])

    def test_pull_request_caches_stay(self):
        a = cache(f"v0-rust-core-Linux-x64-{H1[:8]}-{H2[:8]}", ref="refs/pull/1/merge", created="2026-11-01T00:00:00Z")
        b = cache(f"v0-rust-core-Linux-x64-{H2[:8]}-{H1[:8]}", ref="refs/pull/1/merge")
        self.assertEqual(keys([a, b]), [])

    def test_a_pull_request_does_not_make_main_older(self):
        self.assertEqual(keys([cache(f"pixi-{H1}", ref="refs/pull/2/merge"), cache(f"pixi-{H2}", created="2026-11-01T00:00:00Z")]), [])

    def test_tag_caches_go_after_a_day(self):
        fresh = cache(f"pixi-{H1}", ref="refs/heads/refs/tags/v0.16.0", accessed="2026-11-15T00:00:00Z")
        old = cache(f"pixi-{H2}", ref="refs/heads/refs/tags/v0.15.0", accessed="2026-11-14T00:00:00Z")
        self.assertEqual(keys([fresh, old]), [old["key"]])


if __name__ == "__main__":
    unittest.main()
