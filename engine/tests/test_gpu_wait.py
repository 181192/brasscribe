"""A stage's time waiting for the GPU mutex is recorded apart from the time it ran."""

from __future__ import annotations

import threading
import time

from brasscribe_engine import stages as S
from brasscribe_engine.dag import SOURCE, Executor, Input, Pipeline, Stage
from brasscribe_engine.gpulock import file_lock, is_locked

from .test_dag import session


def heavy_pipeline() -> Pipeline:
    st = [Stage("transcribe.mix.muscriptor", "transcribe", {"audio": Input(SOURCE)}, S.transcribe, adapter="muscriptor",
                params={"output": "mix-ms.mid"}, outputs=("mix-ms.mid",))]
    return Pipeline("test", "test", st, {}, {})


def run_heavy(settings, audio, tmp_path, name):
    cache, adapters = session(settings)
    adapters.gpu_poll = 0.05
    events: list[dict] = []
    res = Executor(cache, adapters, events.append).run(heavy_pipeline(), audio, tmp_path / name)
    return res["transcribe.mix.muscriptor"], events


def waiting_logs(events):
    return [e for e in events if e["type"] == "log" and "waiting for GPU mutex" in e["message"]]


def test_wait_for_the_gpu_mutex_is_not_run_time(settings, audio, tmp_path):
    held = threading.Event()

    def other_job():  # another job holds the GPU for 0.8 s
        with file_lock(settings.gpu_lock):
            held.set()
            time.sleep(0.8)

    t = threading.Thread(target=other_job)
    t.start()
    held.wait(5)
    res, events = run_heavy(settings, audio, tmp_path, "r1")
    t.join()

    assert res.status == "ran"
    assert res.queue_wait_s >= 0.7
    assert res.run_s < res.seconds - 0.7
    assert abs(res.seconds - res.queue_wait_s - res.run_s) < 1e-6
    rec = res.record()
    assert rec["queue_wait_s"] >= 0.7 and rec["run_s"] == round(res.run_s, 3)
    done = [e for e in events if e["type"] == "stage" and e["status"] == "ran"][0]
    assert done["queue_wait_s"] >= 0.7 and done["run_s"] < done["seconds"]
    assert len(waiting_logs(events)) == 1
    assert not is_locked(settings.gpu_lock)


def test_no_wait_is_logged_when_the_gpu_is_free(settings, audio, tmp_path):
    t0 = time.monotonic()
    res, events = run_heavy(settings, audio, tmp_path, "r1")
    assert res.queue_wait_s < 0.05 and time.monotonic() - t0 < 5
    assert waiting_logs(events) == []
