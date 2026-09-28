"""Open job event streams must not take the threads the rest of the API runs on."""

import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from brasscribe_engine.api import create_app
from brasscribe_engine.jobs import Job

STREAMS = 45  # more than the 40 threads Starlette runs sync endpoints on


def test_many_open_event_streams_leave_the_api_responsive(settings):
    app = create_app(settings, trust_loopback=True)
    job = Job("running-job", "test", "t", None, Path("x.wav"), {})
    job.status = "running"
    app.state.jobs.jobs[job.id] = job

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    opened = threading.Barrier(STREAMS + 1, timeout=10)

    def listen():
        with httpx.stream("GET", f"{base}/v1/jobs/{job.id}/events", timeout=30) as r:
            opened.wait()
            for _ in r.iter_raw():
                pass

    listeners = [threading.Thread(target=listen, daemon=True) for _ in range(STREAMS)]
    try:
        for t in listeners:
            t.start()
        opened.wait()
        time.sleep(0.5)  # every stream is now waiting on the job
        t0 = time.perf_counter()
        r = httpx.get(f"{base}/v1/jobs/{job.id}", timeout=5)
        assert r.status_code == 200 and r.json()["status"] == "running"
        assert time.perf_counter() - t0 < 2
    finally:
        job.add_event({"type": "job", "status": "succeeded"})  # ends every stream
        for t in listeners:
            t.join(timeout=5)
        server.should_exit = True
    assert not any(t.is_alive() for t in listeners)
