"""Pair once per device: credentials, server identity, rotation, revocation and the pairing window."""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import companion
from brasscribe_engine.api import create_app
from brasscribe_engine.companion import DeviceRegistry, PairingWindow, PairRequests, clean_name, pairing_uri


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def lan(settings, **kw) -> TestClient:
    return TestClient(create_app(settings, trust_loopback=False, **kw))


def pair(c: TestClient, name: str = "Kalli's iPhone", **headers) -> dict:
    r = c.post("/v1/pair", json={"code": c.app.state.pairing.code, "device_name": name, "platform": "ios"},
               headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def as_owner(c: TestClient):
    """The owner is a loopback client; flip trust for the same app to act as one."""
    class Owner:
        def __enter__(self):
            c.app.state.trust_loopback = True
            return c

        def __exit__(self, *exc):
            c.app.state.trust_loopback = False
    return Owner()


# ---------------------------------------------------------------------------- the regression


def test_token_survives_an_engine_restart(settings):
    with lan(settings) as c:
        p = pair(c)
        server_id = c.get("/v1/health").json()["server_id"]
    with lan(settings) as c:  # a new process on the same data dir, with a new start code
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 200
        h = c.get("/v1/health").json()
        assert h["server_id"] == server_id == p["server_id"]
        assert h["server_name"].startswith("Brasscribe on ")


def test_pair_response_is_all_strings_for_older_apple_clients(settings):
    with lan(settings) as c:
        body = pair(c)
    assert set(body) == {"token", "device_id", "server_id", "server_name"}
    assert all(isinstance(v, str) and v for v in body.values())


def test_every_device_gets_its_own_token(settings):
    with lan(settings) as c:
        a, b = pair(c, "Phone A"), pair(c, "Phone B")
        assert a["token"] != b["token"] and a["device_id"] != b["device_id"]
        assert c.get("/v1/jobs", headers=bearer(a["token"])).status_code == 200
        assert c.get("/v1/jobs", headers=bearer(b["token"])).status_code == 200
        assert c.get("/v1/jobs", headers=bearer("nope")).status_code == 401


def test_pairing_again_with_a_valid_token_keeps_the_same_entry(settings):
    with lan(settings) as c:
        first = pair(c)
        again = pair(c, **bearer(first["token"]))
        assert again["device_id"] == first["device_id"]
        assert c.get("/v1/jobs", headers=bearer(first["token"])).status_code == 401
        with as_owner(c):
            assert len(c.get("/v1/devices").json()) == 1


def test_static_token_still_authenticates(settings):
    settings.token = "script-token"
    with lan(settings) as c:
        assert c.get("/v1/jobs", headers=bearer("script-token")).status_code == 200
        assert c.get("/v1/devices/me", headers=bearer("script-token")).status_code == 404


def test_tokens_are_stored_hashed_and_private(settings):
    with lan(settings) as c:
        p = pair(c)
    path = settings.state_dir / "devices.json"
    stored = path.read_text()
    assert p["token"] not in stored and companion.token_hash(p["token"]) in stored
    if sys.platform != "win32":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"


# ---------------------------------------------------------------------------- this device


def test_devices_me_rotate_and_unpair(settings):
    with lan(settings) as c:
        p = pair(c)
        me = c.get("/v1/devices/me", headers=bearer(p["token"])).json()
        assert me["device_id"] == p["device_id"] and me["name"] == "Kalli's iPhone" and me["platform"] == "ios"
        assert me["rotate_after"] > me["paired_at"] and me["expires_if_idle_after"] > me["last_seen"]

        new = c.post("/v1/devices/me/rotate", headers=bearer(p["token"])).json()
        assert new["device_id"] == p["device_id"] and new["token"] != p["token"]
        # the old token still works until the new one is used (a lost response must not lock the device out)
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 200
        assert c.get("/v1/jobs", headers=bearer(new["token"])).status_code == 200
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 401

        assert c.delete("/v1/devices/me", headers=bearer(new["token"])).status_code == 204
        assert c.get("/v1/jobs", headers=bearer(new["token"])).status_code == 401


def test_previous_token_expires_after_the_grace_period(tmp_path):
    clock = Clock()
    reg = DeviceRegistry(tmp_path / "devices.json", grace_s=600, clock=clock)
    dev, old = reg.pair("Pixel", "android")
    new = reg.rotate(dev.device_id)
    clock.t += 599
    assert reg.authenticate(old) is not None
    clock.t += 2
    assert reg.authenticate(old) is None
    assert reg.authenticate(new) is not None


def test_lost_rotation_responses_never_lock_the_device_out(settings):
    with lan(settings) as c:
        old = pair(c)["token"]
        c.post("/v1/devices/me/rotate", headers=bearer(old))  # response lost: the device still holds `old`
        c.app.state.devices.clock = lambda: time.time() + 3600  # an hour later
        assert c.get("/v1/jobs", headers=bearer(old)).status_code == 200
        c.post("/v1/devices/me/rotate", headers=bearer(old))  # retry, and this response is lost too
        assert c.get("/v1/jobs", headers=bearer(old)).status_code == 200
        newest = c.post("/v1/devices/me/rotate", headers=bearer(old)).json()["token"]
        assert c.get("/v1/jobs", headers=bearer(newest)).status_code == 200
        assert c.get("/v1/jobs", headers=bearer(old)).status_code == 401


def test_idle_devices_are_forgotten(tmp_path):
    clock = Clock()
    reg = DeviceRegistry(tmp_path / "devices.json", idle_days=180, clock=clock)
    _, active = reg.pair("Used", "ios")
    _, idle = reg.pair("Drawer", "ios")
    for _ in range(4):
        clock.t += 60 * 86400
        assert reg.authenticate(active) is not None
    assert reg.authenticate(idle) is None
    assert [d.name for d in reg.list()] == ["Used"]


def test_last_seen_writes_are_throttled(tmp_path):
    clock = Clock()
    reg = DeviceRegistry(tmp_path / "devices.json", clock=clock)
    _, token = reg.pair("Pixel", "android")
    before = (tmp_path / "devices.json").read_text()
    clock.t += 10
    reg.authenticate(token)
    assert (tmp_path / "devices.json").read_text() == before
    clock.t += companion.SEEN_WRITE_S
    reg.authenticate(token)
    assert (tmp_path / "devices.json").read_text() != before


# ---------------------------------------------------------------------------- owner on the computer


def test_owner_lists_and_revokes_devices(settings):
    with lan(settings) as c:
        a, b = pair(c, "Phone A"), pair(c, "Phone B")
        with as_owner(c):
            listed = c.get("/v1/devices").json()
            assert [d["name"] for d in listed] == ["Phone A", "Phone B"]
            assert "token" not in json.dumps(listed) and "hash" not in json.dumps(listed)
            assert c.delete(f"/v1/devices/{a['device_id']}").status_code == 204
            assert c.delete(f"/v1/devices/{a['device_id']}").status_code == 404
        assert c.get("/v1/jobs", headers=bearer(a["token"])).status_code == 401
        assert c.get("/v1/jobs", headers=bearer(b["token"])).status_code == 200


def test_management_is_refused_to_lan_clients_even_when_paired(settings):
    with lan(settings) as c:
        p = pair(c)
        h = bearer(p["token"])
        assert c.get("/v1/devices", headers=h).status_code == 403
        assert c.delete(f"/v1/devices/{p['device_id']}", headers=h).status_code == 403
        assert c.get("/v1/pairing", headers=h).status_code == 403
        assert c.post("/v1/pairing", headers=h).status_code == 403
        assert c.get("/v1/pairing/requests", headers=h).status_code == 403


def test_revocation_from_the_cli_reaches_a_running_engine(settings):
    with lan(settings) as c:
        p = pair(c)
        DeviceRegistry(settings.state_dir / "devices.json").revoke(p["device_id"])  # another process
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 401


def test_reset_forgets_devices_and_changes_the_server_id(settings):
    with lan(settings) as c:
        p = pair(c)
    ident = companion.reset_server(settings.state_dir)
    assert ident.server_id != p["server_id"]
    with lan(settings) as c:
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 401
        assert c.get("/v1/health").json()["server_id"] == ident.server_id


# ---------------------------------------------------------------------------- pairing window and payload


def test_pairing_window_is_single_use_and_expires(settings):
    with lan(settings) as c:
        start_code = c.app.state.pairing.code
        with as_owner(c):
            st = c.post("/v1/pairing", json={"ttl_s": 600}).json()
        assert st["open"] and st["single_use"] and st["code"] != "" and st["expires_at"]
        assert c.post("/v1/pair", json={"code": start_code}).status_code == 403 or st["code"] == start_code
        assert c.post("/v1/pair", json={"code": st["code"]}).status_code == 200
        assert c.post("/v1/pair", json={"code": st["code"]}).status_code == 403  # used up
        with as_owner(c):
            assert c.get("/v1/pairing").json()["open"] is False
            st = c.post("/v1/pairing", json={"ttl_s": 600}).json()
            c.app.state.pairing.expires_at = 0  # time passes
            assert c.get("/v1/pairing").json()["open"] is False
            st = c.post("/v1/pairing", json={"ttl_s": 600}).json()
            ext = c.post("/v1/pairing", json={"ttl_s": 900, "extend": True}).json()
            assert ext["code"] == st["code"] and ext["expires_at"] > st["expires_at"]
            assert c.delete("/v1/pairing").json()["open"] is False
        assert c.post("/v1/pair", json={"code": st["code"]}).status_code == 403


def test_pairing_payload_uri(settings):
    with lan(settings) as c:
        c.app.state.hosts = ["192.168.1.20:8765", "10.0.0.5:8765"]
        with as_owner(c):
            st = c.get("/v1/pairing").json()
    u = urlsplit(st["uri"])
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert (u.scheme, u.netloc) == ("brasscribe", "pair")
    assert q == {"v": "1", "id": st["server_id"], "name": st["server_name"], "h": "192.168.1.20:8765,10.0.0.5:8765",
                 "code": st["code"]}
    assert st["fingerprint"] is None
    assert "fp=" in pairing_uri("abc", "Brasscribe on x", [], None, fingerprint="Zm9v")


def test_serve_banner_records_hosts_for_the_payload(settings):
    from brasscribe_engine.cli import serve_banner

    app = create_app(settings)
    _, lines = serve_banner(app, "0.0.0.0", 8765, ips=["192.168.1.20"])
    assert app.state.hosts == ["192.168.1.20:8765"]
    assert any(app.state.pairing.code in line for line in lines)


# ---------------------------------------------------------------------------- approve on the computer


def test_approve_on_the_computer(settings):
    with lan(settings) as c:
        req = c.post("/v1/pair/requests", json={"device_name": "Pixel 9", "platform": "android"})
        assert req.status_code == 202
        rid, match = req.json()["request_id"], req.json()["match_code"]
        assert c.get(f"/v1/pair/requests/{rid}").json()["status"] == "pending"
        with as_owner(c):
            [shown] = c.get("/v1/pairing/requests").json()
            assert shown["name"] == "Pixel 9" and shown["match_code"] == match
            assert c.post(f"/v1/pairing/requests/{rid}/approve").json()["status"] == "approved"
        got = c.get(f"/v1/pair/requests/{rid}").json()
        assert got["status"] == "approved" and got["server_id"] == c.get("/v1/health").json()["server_id"]
        assert c.get("/v1/jobs", headers=bearer(got["token"])).status_code == 200
        assert c.get(f"/v1/pair/requests/{rid}").status_code == 404  # the token is handed out once


def test_denied_and_capped_requests(settings):
    with lan(settings) as c:
        ids = [c.post("/v1/pair/requests", json={"device_name": f"p{i}"}).json()["request_id"] for i in range(3)]
        assert c.post("/v1/pair/requests", json={"device_name": "p3"}).status_code == 429
        with as_owner(c):
            assert c.post(f"/v1/pairing/requests/{ids[0]}/deny").json()["status"] == "denied"
            assert c.post(f"/v1/pairing/requests/{ids[0]}/approve").status_code == 404
        r = c.get(f"/v1/pair/requests/{ids[0]}").json()
        assert r == {"status": "denied", "token": None, "device_id": None, "server_id": None, "server_name": None}


def test_requests_expire():
    clock = Clock()
    reqs = PairRequests(clock=clock)
    r = reqs.create("Phone", "ios")
    clock.t += companion.REQUEST_S + 1
    assert reqs.poll(r.request_id) is None and reqs.pending() == []


# ---------------------------------------------------------------------------- small pieces


@pytest.mark.parametrize("raw, shown", [
    ("  Kalli's\niPhone\t", "Kalli's iPhone"),
    ("\x1b[31mred\x07", "[31mred"),
    ("", "Unnamed device"),
    (None, "Unnamed device"),
    ("x" * 200, "x" * 64),
])
def test_device_names_are_cleaned(raw, shown):
    assert clean_name(raw) == shown


def test_lockout_backs_off():
    clock = Clock()
    w = PairingWindow(clock=clock)
    wrong = "x"
    waits = []
    for _ in range(3):
        for _ in range(companion.LOCK_AFTER):
            assert w.check(wrong) == "wrong"
        assert w.check(w.code) == "locked"
        waits.append(w.retry_after())
        clock.t = w.locked_until
    assert waits == [30.0, 60.0, 120.0]
    assert w.check(w.code) == "ok"
