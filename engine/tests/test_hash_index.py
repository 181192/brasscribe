"""Processes sharing one file-hash index save it without crashing or losing each other's entries."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from brasscribe_engine.hashing import HashIndex

WRITER = textwrap.dedent("""
    import sys
    from pathlib import Path
    from brasscribe_engine.hashing import HashIndex
    index, files, rounds = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    h = HashIndex(index)
    for f in sorted(files.iterdir()):
        h.file(f)
        for _ in range(rounds):
            h.save()
    print("done", flush=True)
""")


@pytest.mark.slow
def test_two_processes_save_one_index(tmp_path):
    index = tmp_path / "cache" / "file-hashes.json"
    dirs = []
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        for i in range(40):
            (d / f"{i}.bin").write_bytes(f"{name}{i}".encode())
        dirs.append(d)
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(index), str(d), "5"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for d in dirs]
    outs = [p.communicate(timeout=120) for p in procs]
    for p, (out, err) in zip(procs, outs):
        assert p.returncode == 0, err
        assert out.strip() == "done"
    saved = json.loads(index.read_text())
    for d in dirs:
        for f in d.iterdir():
            assert str(f.resolve()) in saved, f
    assert not list(index.parent.glob("*.tmp"))  # every writer's temp file was replaced or removed
    assert HashIndex(index).file(dirs[0] / "0.bin") == saved[str((dirs[0] / "0.bin").resolve())][2]


def test_save_keeps_entries_another_process_wrote(tmp_path):
    index = tmp_path / "file-hashes.json"
    f1, f2 = tmp_path / "one", tmp_path / "two"
    f1.write_text("1")
    f2.write_text("2")
    a, b = HashIndex(index), HashIndex(index)  # both loaded the empty index
    a.file(f1)
    a.save()
    b.file(f2)
    b.save()  # without the merge, this dropped a's entry
    saved = json.loads(index.read_text())
    assert str(f1.resolve()) in saved and str(f2.resolve()) in saved
