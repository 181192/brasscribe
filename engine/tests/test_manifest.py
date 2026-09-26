import json

import pytest

from brasscribe_engine import runner


def test_run_writes_manifest_and_outputs(settings, audio, tmp_path):
    out = tmp_path / "out"
    m = runner.run(settings, audio, "test", out=out)
    assert m["status"] == "succeeded"
    run_dir = settings.runs_dir / m["run_id"]
    disk = json.loads((run_dir / "manifest.json").read_text())
    assert disk == m
    assert m["input"]["sha256"] and m["input"]["path"] == str(audio)
    assert set(m["git"]) == {"sha", "branch", "dirty"}
    assert m["host"]["device"] in ("cpu", "mps", "cuda")
    assert m["title"] == "Song test"
    st = {s["stage"]: s for s in m["stages"]}
    assert st["transcribe.mix.swift-f0"]["adapter"]["version"] == "9.9.9"
    assert st["transcribe.mix.swift-f0"]["adapter"]["fingerprint"]
    assert set(m["outputs"]) == {"composition.json", "brass-band.musicxml"}
    assert (out / "composition.json").read_bytes() == (run_dir / "outputs" / "composition.json").read_bytes()
    assert (out / "manifest.json").exists()
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    assert [e["id"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1] == {**events[-1], "type": "job", "status": "succeeded"}


def test_rerun_reproduces_outputs(settings, audio):
    m = runner.run(settings, audio, "test")
    old, new = runner.rerun(settings, settings.runs_dir / m["run_id"] / "manifest.json", cold={"all"})
    assert new["status"] == "succeeded" and new["run_id"] != old["run_id"]
    assert all(s["status"] == "ran" and s["matches_cache"] for s in new["stages"])
    d = runner.diff_manifests(old, new)
    assert d["outputs_different"] == [] and d["stages_different"] == []


def test_rerun_refuses_changed_input(settings, audio):
    m = runner.run(settings, audio, "test")
    audio.write_bytes(b"edited")
    with pytest.raises(runner.RunRefused):
        runner.rerun(settings, settings.runs_dir / m["run_id"] / "manifest.json")


def test_refuses_golden_output_dir(settings, audio):
    with pytest.raises(runner.RunRefused):
        runner.run(settings, audio, "test", out=settings.golden_dir / "x")


def test_failed_run_manifest(settings, audio, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "1")
    m = runner.run(settings, audio, "test")
    assert m["status"] == "failed" and "swift-f0" in m["error"]
    assert m["stages"][0]["status"] == "failed"
    assert m["outputs"] == {}
