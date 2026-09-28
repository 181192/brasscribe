import threading

import pytest

from brasscribe_engine import stages as S
from brasscribe_engine.adapters import AdapterRegistry
from brasscribe_engine.cache import ArtifactCache
from brasscribe_engine.gpulock import is_locked
from brasscribe_engine.dag import SOURCE, Cancelled, Executor, Input, Pipeline, Stage, StageFailed
from brasscribe_engine.hashing import HashIndex

from .conftest import fake_pipeline


def session(settings):
    hashes = HashIndex(settings.cache_dir / "h.json")
    cache = ArtifactCache(settings.cache_dir, hashes)
    return cache, AdapterRegistry(settings.adapters_dir, settings.models_dir, hashes, settings.gpu_lock)


def run(settings, audio, tmp_path, name="r1", pipeline=None, **kw):
    cache, adapters = session(settings)
    events = []
    ex = Executor(cache, adapters, events.append, **kw)
    res = ex.run(pipeline or fake_pipeline("T", {}), audio, tmp_path / name)
    return res, events


def test_first_run_runs_second_run_hits_cache(settings, audio, tmp_path):
    r1, ev = run(settings, audio, tmp_path, "r1")
    assert [r.status for r in r1.values()] == ["ran", "ran", "ran"]
    assert (r1["transcribe.mix.swift-f0"].out_dir / "mix-sw.mid").read_bytes() == b"RIFF-fake-audioswift-f0"
    r2, _ = run(settings, audio, tmp_path, "r2")
    assert [r.status for r in r2.values()] == ["cached", "cached", "cached"]
    assert {k: r.key for k, r in r1.items()} == {k: r.key for k, r in r2.items()}
    fractions = [e["fraction"] for e in ev if e["type"] == "stage" and e["status"] != "started"]
    assert fractions == pytest.approx([1 / 3, 2 / 3, 1.0], abs=1e-3)


def test_key_depends_on_input_params_and_adapter(settings, audio, tmp_path):
    r1, _ = run(settings, audio, tmp_path, "r1")
    audio.write_bytes(b"other audio")
    r2, _ = run(settings, audio, tmp_path, "r2")
    assert r2["transcribe.mix.swift-f0"].key != r1["transcribe.mix.swift-f0"].key
    r3, _ = run(settings, audio, tmp_path, "r3", pipeline=fake_pipeline("Other title", {}))
    assert r3["arrange"].key != r2["arrange"].key and r3["arrange"].status == "ran"
    assert r3["transcribe.mix.swift-f0"].status == "cached"
    (settings.adapters_dir / "swift-f0" / "uv.lock").write_text("changed")
    r4, _ = run(settings, audio, tmp_path, "r4")
    assert r4["transcribe.mix.swift-f0"].status == "ran"
    assert r4["transcribe.mix.basic-pitch"].status == "cached"


def test_cold_stage_is_compared_with_cache(settings, audio, tmp_path):
    run(settings, audio, tmp_path, "r1")
    r2, ev = run(settings, audio, tmp_path, "r2", cold={"transcribe.mix.swift-f0", "arrange"})
    assert r2["transcribe.mix.swift-f0"].status == "ran" and r2["transcribe.mix.swift-f0"].matches_cache is True
    assert r2["transcribe.mix.basic-pitch"].status == "cached"
    assert r2["arrange"].matches_cache is True
    assert any(e.get("matches_cache") for e in ev)


def test_reuse_imports_only_when_inputs_match(settings, audio, tmp_path):
    reuse = tmp_path / "old-run"
    (reuse / "layers").mkdir(parents=True)
    (reuse / "layers" / "mix-sw.mid").write_bytes(b"precomputed sw")
    (reuse / "layers" / "mix-bp.mid").write_bytes(b"precomputed bp")
    r, _ = run(settings, audio, tmp_path, "r1", reuse_dir=reuse)
    assert r["transcribe.mix.swift-f0"].status == "imported"
    assert r["transcribe.mix.swift-f0"].provenance["imported_from"].endswith("layers")
    assert (r["transcribe.mix.swift-f0"].out_dir / "mix-sw.mid").read_bytes() == b"precomputed sw"
    # arrange has no reuse layout, so it runs on the imported inputs
    assert r["arrange"].status == "ran"


def test_reuse_rejected_when_upstream_differs(settings, audio, tmp_path):
    reuse = tmp_path / "old"
    (reuse / "stems").mkdir(parents=True)
    (reuse / "stems" / "a.txt").write_text("OLD")
    (reuse / "down").mkdir()
    (reuse / "down" / "b.txt").write_text("from OLD")

    def up(ctx):
        (ctx.out / "a.txt").write_text("NEW")

    def down(ctx):
        (ctx.out / "b.txt").write_text("from " + ctx.inputs["a"].read_text())

    p = Pipeline("t", "t", [
        Stage("up", "stems", {"audio": Input(SOURCE)}, up, outputs=("a.txt",)),  # no reuse layout: always runs
        Stage("down", "layers", {"a": Input("up", "a.txt")}, down, outputs=("b.txt",), reuse_subdir="down"),
    ], {})
    r, _ = run(settings, audio, tmp_path, "r1", pipeline=p, reuse_dir=reuse)
    assert r["down"].status == "ran"
    assert (r["down"].out_dir / "b.txt").read_text() == "from NEW"


def test_heavy_adapter_refused_without_heavy(settings, audio, tmp_path):
    p = Pipeline("t", "t", [Stage("transcribe.mix.muscriptor", "transcribe", {"audio": Input(SOURCE)}, S.transcribe,
                                  adapter="muscriptor", params={"output": "m.mid"}, outputs=("m.mid",))], {})
    with pytest.raises(StageFailed, match="heavy runs are disabled"):
        run(settings, audio, tmp_path, "r1", pipeline=p, allow_heavy=False)
    r, _ = run(settings, audio, tmp_path, "r2", pipeline=p)
    assert r["transcribe.mix.muscriptor"].status == "ran"
    assert not is_locked(settings.gpu_lock)  # mutex released
    r, _ = run(settings, audio, tmp_path, "r3", pipeline=p, allow_heavy=False)
    assert r["transcribe.mix.muscriptor"].status == "cached"


def test_failure_is_reported(settings, audio, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "1")
    cache, adapters = session(settings)
    events = []
    ex = Executor(cache, adapters, events.append)
    with pytest.raises(StageFailed, match="swift-f0 failed"):
        ex.run(fake_pipeline("T", {}), audio, tmp_path / "r")
    assert ex.results["transcribe.mix.swift-f0"].status == "failed"
    assert events[-1]["status"] == "failed" and "boom" in events[-1]["error"]


def test_cancel_between_stages(settings, audio, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        run(settings, audio, tmp_path, "r", cancel=cancel)


def test_profiles_build_valid_dags(tmp_path):
    from brasscribe_engine import profiles

    for name in profiles.PROFILES:
        p = profiles.build(name, tmp_path / "x.wav")
        seen = set()
        for s in p.stages:
            for inp in s.inputs.values():
                assert inp.stage == SOURCE or inp.stage in seen, (name, s.name, inp)
            seen.add(s.name)
        assert all(stage in seen for stage, _ in p.outputs.values())
    assert profiles.default_title("orchestra-with-soloist", tmp_path / "mikkel.wav") == \
        "Mikkel — solo cornet & brass band (draft)"
