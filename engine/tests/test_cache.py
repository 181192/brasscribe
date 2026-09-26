import os
import stat

from brasscribe_engine.cache import ArtifactCache
from brasscribe_engine.hashing import HashIndex, source_fingerprint


def test_store_lookup_materialize(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("alpha")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("beta")
    cache = ArtifactCache(tmp_path / "cache")
    assert cache.lookup("k1") is None
    e = cache.store("k1", "stage", src, provenance={"imported_from": str(src)})
    assert set(e.files) == {"a.txt", "sub/b.txt"}
    again = cache.lookup("k1")
    assert again.files == e.files and again.provenance["imported_from"] == str(src)
    dest = tmp_path / "run"
    cache.materialize(e, dest)
    assert (dest / "sub" / "b.txt").read_text() == "beta"
    assert cache.verify(e) == []


def test_entries_are_read_only_and_sources_untouched(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    f.write_text("alpha")
    before = f.stat().st_mode
    cache = ArtifactCache(tmp_path / "cache")
    e = cache.store("k", "stage", src)
    stored = cache.path(e, "a.txt")
    assert not stored.stat().st_mode & stat.S_IWUSR
    assert f.stat().st_mode == before  # imports are cloned, never hardlinked
    assert os.stat(stored).st_ino != f.stat().st_ino


def test_store_is_idempotent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a").write_text("1")
    cache = ArtifactCache(tmp_path / "cache")
    e1 = cache.store("k", "s", src)
    (src / "a").write_text("2")
    e2 = cache.store("k", "s", src)
    assert e1.files == e2.files  # first writer wins; entries never change


def test_hash_index_memoises_and_notices_changes(tmp_path):
    f = tmp_path / "x"
    f.write_text("one")
    idx = HashIndex(tmp_path / "idx.json")
    h1 = idx.file(f)
    idx.save()
    assert HashIndex(tmp_path / "idx.json").file(f) == h1
    f.write_text("two!")
    assert idx.file(f) != h1


def test_source_fingerprint_tracks_content(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "m.py").write_text("x = 1\n")
    a = source_fingerprint(pkg)
    (pkg / "m.py").write_text("x = 2\n")
    assert source_fingerprint(pkg) != a
