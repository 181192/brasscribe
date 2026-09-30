"""A model that hangs is stopped, with everything it started: when its job is cancelled, and at its time limit."""

from __future__ import annotations

import os
import threading
import time

import pytest

from brasscribe_engine import jobs as J
from brasscribe_engine import stages as S
from brasscribe_engine.adapters import AdapterCancelled, AdapterError
from brasscribe_engine.dag import SOURCE, Cancelled, Executor, Input, Pipeline, Stage
from brasscribe_engine.gpulock import file_lock, is_locked
from brasscribe_engine.jobs import JobManager

from .test_dag import session


def gone(pid: int, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def wait_for(path, timeout: float = 20.0) -> int:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.read_text().strip():
            return int(path.read_text())
        time.sleep(0.02)
    raise AssertionError("the fake model never started")


def heavy_pipeline() -> Pipeline:
    return Pipeline("t", "t", [Stage("transcribe.mix.muscriptor", "transcribe", {"audio": Input(SOURCE)}, S.transcribe,
                                     adapter="muscriptor", params={"output": "m.mid"}, outputs=("m.mid",))], {})


@pytest.mark.slow
def test_cancel_stops_a_hanging_model_and_frees_the_gpu(settings, audio, tmp_path, monkeypatch):
    pid_file = tmp_path / "model.pid"
    monkeypatch.setenv("FAKE_HANG", str(pid_file))
    cache, adapters = session(settings)
    cancel = threading.Event()
    ex = Executor(cache, adapters, cancel=cancel)
    raised: list[BaseException] = []

    def go():
        try:
            ex.run(heavy_pipeline(), audio, tmp_path / "r")
        except BaseException as e:  # noqa: BLE001 - checked below
            raised.append(e)

    t = threading.Thread(target=go)
    t.start()
    model = wait_for(pid_file)
    assert is_locked(settings.gpu_lock)
    cancel.set()
    t.join(15)
    assert not t.is_alive() and isinstance(raised[0], Cancelled)
    assert gone(model), "the model the adapter started is still running"
    assert not is_locked(settings.gpu_lock)


@pytest.mark.slow
def test_cancelling_a_running_job_ends_it_as_cancelled(settings, audio, tmp_path, monkeypatch):
    pid_file = tmp_path / "model.pid"
    monkeypatch.setenv("FAKE_HANG", str(pid_file))
    jobs = JobManager(settings)
    job = jobs.submit(audio, "test")
    model = wait_for(pid_file)
    t0 = time.time()
    jobs.cancel(job.id)
    while job.status not in J.TERMINAL and time.time() - t0 < 15:
        time.sleep(0.02)
    assert job.status == "cancelled" and time.time() - t0 < 10
    assert gone(model)
    assert jobs.get(job.id).status == "cancelled"


@pytest.mark.slow
def test_a_model_past_its_time_limit_is_stopped(settings, audio, tmp_path, monkeypatch):
    pid_file = tmp_path / "model.pid"
    monkeypatch.setenv("FAKE_HANG", str(pid_file))
    monkeypatch.setenv("BRASSCRIBE_ADAPTER_TIMEOUT_S", "1")
    from brasscribe_engine.config import Settings

    assert Settings().adapter_timeout_s == 1.0
    _, adapters = session(settings)
    adapters.timeout_s = 1.0
    t0 = time.time()
    with pytest.raises(AdapterError, match="time limit"):
        adapters.run("swift-f0", audio, tmp_path / "out.mid")
    assert time.time() - t0 < 10
    assert gone(wait_for(pid_file))


def test_time_limits_by_weight(settings):
    from brasscribe_engine.adapters import HEAVY_TIMEOUT_S, LIGHT_TIMEOUT_S

    _, adapters = session(settings)
    assert adapters.time_limit("muscriptor") == HEAVY_TIMEOUT_S > adapters.time_limit("swift-f0") == LIGHT_TIMEOUT_S
    adapters.timeout_s = 5.0
    assert adapters.time_limit("muscriptor") == adapters.time_limit("swift-f0") == 5.0


def test_cancel_while_waiting_for_the_gpu(settings, audio, tmp_path):
    _, adapters = session(settings)
    adapters.gpu_poll = 0.02
    cancel = threading.Event()
    with file_lock(settings.gpu_lock):  # another process has the GPU
        threading.Timer(0.2, cancel.set).start()
        with pytest.raises(AdapterCancelled, match="waited for the GPU"):
            adapters.run("muscriptor", audio, tmp_path / "m.mid", cancel=cancel)
