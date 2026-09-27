import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import openapi
from brasscribe_engine.api import create_app

ENGINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def wait(client, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/v1/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def sse(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "data" in fields:
            out.append({"id": int(fields["id"]), "event": fields["event"], "data": json.loads(fields["data"])})
    return out


def test_health_and_profiles(client):
    h = client.get("/v1/health").json()
    assert h["status"] == "ok" and h["auth_required"] is False
    names = {p["name"]: p for p in client.get("/v1/profiles").json()}
    assert {"solo", "brass-band", "pop-rock", "orchestra-with-soloist"} <= set(names)
    assert names["orchestra-with-soloist"]["validated"] is True
    assert "transcribe.solo.swift-f0" in names["orchestra-with-soloist"]["stages"]


def test_upload_job_stream_and_fetch(client, audio):
    ref = client.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes(), "audio/wav")})
    assert ref.status_code == 201
    audio_id = ref.json()["audio_id"]
    r = client.post("/v1/jobs", json={"audio_id": audio_id, "profile": "test"})
    assert r.status_code == 202
    job = r.json()
    assert job["title"] == "Song test" and job["status"] in ("queued", "running", "succeeded")
    done = wait(client, job["id"])
    assert done["status"] == "succeeded" and done["progress"] == 1.0
    assert all(s["status"] == "ran" for s in done["stages"])

    events = sse(client.get(f"/v1/jobs/{job['id']}/events").text)
    assert events[0]["data"]["status"] == "queued"
    assert events[-1]["event"] == "job" and events[-1]["data"]["status"] == "succeeded"
    ids = [e["id"] for e in events]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    stage_done = [e["data"] for e in events if e["event"] == "stage" and e["data"]["status"] == "ran"]
    assert stage_done[-1]["fraction"] == 1.0
    resumed = sse(client.get(f"/v1/jobs/{job['id']}/events", headers={"Last-Event-ID": str(ids[-3])}).text)
    assert [e["id"] for e in resumed] == ids[-2:]

    comp = client.get(f"/v1/jobs/{job['id']}/composition")
    assert comp.status_code == 200 and comp.json()["title"] == "Song test"
    assert client.get(f"/v1/jobs/{job['id']}/musicxml").headers["content-type"].startswith("application/vnd.recordare")
    assert client.get(f"/v1/jobs/{job['id']}/pdf").status_code == 404  # test profile has no export stage
    arts = {a["name"] for a in client.get(f"/v1/jobs/{job['id']}/artifacts").json()}
    assert arts == {"composition.json", "brass-band.musicxml"}
    assert client.get(f"/v1/jobs/{job['id']}/manifest").json()["run_id"] == job["id"]
    assert client.get(f"/v1/jobs/{job['id']}/artifacts/..%2Fmanifest.json").status_code == 404
    assert job["id"] in {j["id"] for j in client.get("/v1/jobs").json()}


def test_one_shot_upload_and_second_job_hits_cache(client, audio):
    r = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
    assert r.status_code == 202
    wait(client, r.json()["id"])
    r2 = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
    j = wait(client, r2.json()["id"])
    assert all(s["status"] == "cached" for s in j["stages"])


def test_errors(client):
    assert client.get("/v1/jobs/nope").status_code == 404
    assert client.post("/v1/jobs", json={"audio_id": "missing", "profile": "test"}).status_code == 404
    ref = client.post("/v1/audio", files={"file": ("a.wav", b"x")}).json()
    assert client.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "nope"}).status_code == 422


def test_lan_clients_must_pair(settings):
    with TestClient(create_app(settings, trust_loopback=False)) as c:
        assert c.get("/v1/health").json()["auth_required"] is True
        assert c.get("/v1/jobs").status_code == 401
        assert c.post("/v1/pair", json={"code": "not-it"}).status_code == 403
        token = c.post("/v1/pair", json={"code": c.app.state.pairing.code}).json()["token"]
        assert c.get("/v1/jobs", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert c.get("/v1/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_wrong_codes_lock_pairing_but_never_change_the_code_on_screen(settings):
    with TestClient(create_app(settings, trust_loopback=False)) as c:
        code = c.app.state.pairing.code
        statuses = [c.post("/v1/pair", json={"code": "000000" if code != "000000" else "111111"}).status_code
                    for _ in range(6)]
        assert statuses == [403] * 5 + [429]
        r = c.post("/v1/pair", json={"code": code})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
        assert c.app.state.pairing.code == code
        c.app.state.pairing.locked_until = 0  # the lock has passed
        assert c.post("/v1/pair", json={"code": code}).status_code == 200


def test_studio_placeholder_served(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")


def test_committed_openapi_matches_app():
    committed = (ENGINE / "openapi.json").read_text()
    assert committed == openapi.render(), "engine/openapi.json is stale: run `pixi run openapi`"


def test_serve_banner_lists_lan_url_and_pairing_code(settings):
    from brasscribe_engine.cli import serve_banner

    app = create_app(settings)
    url, lines = serve_banner(app, "0.0.0.0", 8765)
    assert url == "http://127.0.0.1:8765/"
    assert any(line.startswith("LAN URL: ") for line in lines)
    assert any(app.state.pairing.code in line for line in lines)
    assert serve_banner(app, "127.0.0.1", 8765)[1] == ["brasscribe engine on http://127.0.0.1:8765/"]


def test_job_names_the_paired_device_that_started_it(settings, audio):
    with TestClient(create_app(settings, trust_loopback=False)) as c:
        token = c.post("/v1/pair", json={"code": c.app.state.pairing.code,
                                          "device_name": "Kari's iPhone", "platform": "ios"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        r = c.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"},
                   headers=h)
        assert r.status_code == 202 and r.json()["device_name"] == "Kari's iPhone"
        job = wait_with(c, r.json()["id"], h)
        rerun = c.post(f"/v1/jobs/{job['id']}/rerun", headers=h).json()
        assert rerun["device_name"] == "Kari's iPhone"


def test_job_from_the_engines_own_computer_has_no_device_name(client, audio):
    r = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
    assert r.json()["device_name"] is None
    wait(client, r.json()["id"])


def wait_with(client, job_id, headers, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")
