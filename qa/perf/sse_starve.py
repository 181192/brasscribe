"""How long a plain API call waits while N job event streams are open.

    pixi run python qa/perf/sse_starve.py 10 39 41 60

Runs the engine app under uvicorn on a free port with an empty data directory and one fake
running job, opens N event streams on it, then times GET /v1/health. Before the streams had
threads of their own, the 41st stream took the last thread of Starlette's pool.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from brasscribe_engine.api import create_app
from brasscribe_engine.config import Settings
from brasscribe_engine.jobs import Job

app = create_app(Settings(data_dir=Path(tempfile.mkdtemp())), trust_loopback=True)
job = Job("fake-running", "solo", "t", None, Path("x.wav"), {})
job.status = "running"
app.state.jobs.jobs[job.id] = job

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
base = f"http://127.0.0.1:{port}"
while not server.started:
    time.sleep(0.05)


def hold(stop: threading.Event) -> None:
    with httpx.stream("GET", f"{base}/v1/jobs/{job.id}/events", timeout=None) as r:
        for _ in r.iter_raw():
            if stop.is_set():
                return


for n in map(int, sys.argv[1:] or ["41"]):
    stop = threading.Event()
    for _ in range(n):
        threading.Thread(target=hold, args=(stop,), daemon=True).start()
    time.sleep(2.0)
    t0 = time.perf_counter()
    try:
        r = httpx.get(base + "/v1/health", timeout=20)
        print(f"streams={n:3d}  /v1/health {r.status_code} in {(time.perf_counter() - t0) * 1000:.0f} ms", flush=True)
    except httpx.TimeoutException:
        print(f"streams={n:3d}  /v1/health timed out after 20 s", flush=True)
    stop.set()
    job.add_event({"type": "log", "message": "wake"})  # the streams notice the stop flag and close
    time.sleep(16)
server.should_exit = True
