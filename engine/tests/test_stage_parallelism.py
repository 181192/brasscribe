"""Bounded stage parallelism: independent stages overlap, GPU stages never do, the manifest keeps pipeline order."""

from __future__ import annotations

import threading
import time

import pytest

from brasscribe_engine.dag import SOURCE, Executor, Input, Pipeline, StageFailed, Stage

from .test_dag import session

SLEEP = 0.4


class Spans:
    def __init__(self):
        self.lock = threading.Lock()
        self.spans: dict[str, tuple[float, float]] = {}

    def stage(self, name: str, heavy: bool = False, inputs: dict[str, Input] | None = None, fail: bool = False) -> Stage:
        def run(ctx):
            t0 = time.monotonic()
            if heavy:  # a GPU stage takes the machine-wide mutex, as an adapter call does
                with ctx.executor.adapters.gpu_mutex(poll=0.02):
                    time.sleep(SLEEP)
            else:
                time.sleep(SLEEP)
            with self.lock:
                self.spans[name] = (t0, time.monotonic())
            if fail:
                raise RuntimeError("boom")
            (ctx.out / f"{name}.txt").write_text(name)

        # the adapter only marks the stage as heavy or not for the scheduler; run() does not call it
        return Stage(name, "transcribe", inputs or {"audio": Input(SOURCE)}, run,
                     adapter="muscriptor" if heavy else "swift-f0", outputs=(f"{name}.txt",))

    def overlap(self, a: str, b: str) -> bool:
        (a0, a1), (b0, b1) = self.spans[a], self.spans[b]
        return a0 < b1 - 0.05 and b0 < a1 - 0.05


def pipeline(sp: Spans, fail: bool = False) -> Pipeline:
    st = [sp.stage("gpu1", heavy=True), sp.stage("cpu1"), sp.stage("gpu2", heavy=True), sp.stage("cpu2", fail=fail),
          sp.stage("after", inputs={"a": Input("gpu1", "gpu1.txt"), "b": Input("cpu1", "cpu1.txt")})]
    return Pipeline("test", "test", st, {}, {})


def run(settings, audio, tmp_path, parallelism, fail=False):
    cache, adapters = session(settings)
    sp = Spans()
    events: list[dict] = []
    ex = Executor(cache, adapters, events.append, parallelism=parallelism)
    t0 = time.monotonic()
    try:
        res = ex.run(pipeline(sp, fail), audio, tmp_path / f"p{parallelism}")
    finally:
        wall = time.monotonic() - t0
    return res, sp, wall, events


def test_one_runs_stages_in_order(settings, audio, tmp_path):
    res, sp, wall, _ = run(settings, audio, tmp_path, 1)
    assert list(res) == ["gpu1", "cpu1", "gpu2", "cpu2", "after"]
    assert not any(sp.overlap(a, b) for a in sp.spans for b in sp.spans if a < b)
    assert wall >= 5 * SLEEP


def test_two_overlaps_cpu_with_gpu_but_never_two_gpu_stages(settings, audio, tmp_path):
    res, sp, wall, events = run(settings, audio, tmp_path, 2)
    assert list(res) == ["gpu1", "cpu1", "gpu2", "cpu2", "after"]  # pipeline order, not finishing order
    assert all(r.status == "ran" for r in res.values())
    assert sp.overlap("gpu1", "cpu1")
    assert not sp.overlap("gpu1", "gpu2")
    assert sp.spans["after"][0] >= max(sp.spans["gpu1"][1], sp.spans["cpu1"][1])
    assert wall < 4.5 * SLEEP  # 5 stages of SLEEP in 3 rounds (in order: 5 SLEEP or more)
    fractions = [e["fraction"] for e in events if e["type"] == "stage" and e["status"] == "ran"]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert not settings.gpu_lock.exists()


def test_a_failed_stage_fails_the_run_after_the_others_finish(settings, audio, tmp_path):
    with pytest.raises(StageFailed, match="cpu2"):
        run(settings, audio, tmp_path, 3, fail=True)
