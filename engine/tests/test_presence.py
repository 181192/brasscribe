"""Presence (last_seen, online, /v1/status), the server name, and the local-trust switch."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import companion, discovery
from brasscribe_engine.api import create_app
from brasscribe_engine.companion import DeviceRegistry
from brasscribe_engine.config import Settings
from brasscribe_engine.jobs import Job

from .test_companion import Clock, as_owner, bearer, lan, pair

ADMIN = "admin-" + "x" * 40
REAL_OS_COMPUTER_NAME = discovery.os_computer_name.__wrapped__  # the autouse fixture replaces the cached one


def on_disk(settings: Settings) -> dict[str, dict]:
    return {d["device_id"]: d for d in json.loads((settings.state_dir / "devices.json").read_text())["devices"]}


# ---------------------------------------------------------------------------- presence


def test_every_request_marks_the_device_seen_and_online(settings):
    with lan(settings) as c:
        clock = c.app.state.devices.clock = Clock()
        p = pair(c)
        clock.t += 3600  # an hour later: not online any more
        with as_owner(c):
            (d,) = c.get("/v1/devices").json()
        assert d["online"] is False
        assert c.get("/v1/devices/me", headers=bearer(p["token"])).json()["online"] is True
        with as_owner(c):
            (d,) = c.get("/v1/devices").json()
        assert d["online"] is True and d["last_seen"] == companion.iso(clock.t)
        clock.t += companion.ONLINE_S + 1
        with as_owner(c):
            assert c.get("/v1/devices").json()[0]["online"] is False


def test_last_seen_stays_in_memory_until_the_flush_interval_or_shutdown(settings):
    with lan(settings) as c:
        clock = c.app.state.devices.clock = Clock()
        p = pair(c)
        paired = on_disk(settings)[p["device_id"]]["last_seen"]
        clock.t += 10
        c.get("/v1/devices/me", headers=bearer(p["token"]))
        assert on_disk(settings)[p["device_id"]]["last_seen"] == paired  # no write per request
        clock.t += companion.SEEN_FLUSH_S
        c.get("/v1/devices/me", headers=bearer(p["token"]))
        assert on_disk(settings)[p["device_id"]]["last_seen"] == clock.t
        clock.t += 5
        c.get("/v1/devices/me", headers=bearer(p["token"]))
        assert on_disk(settings)[p["device_id"]]["last_seen"] == clock.t - 5
    assert on_disk(settings)[p["device_id"]]["last_seen"] == clock.t  # flushed when the engine stopped


def test_a_revoke_from_another_process_survives_the_engines_presence_flush(tmp_path):
    clock = Clock()
    engine = DeviceRegistry(tmp_path / "devices.json", clock=clock)
    a, token_a = engine.pair("Phone A", "ios")
    b, token_b = engine.pair("Phone B", "android")
    clock.t += 5
    assert engine.authenticate(token_a)  # unflushed last_seen for A
    assert engine.authenticate(token_b)
    DeviceRegistry(tmp_path / "devices.json", clock=clock).revoke(a.device_id)  # `brasscribe devices revoke`
    engine.flush()
    assert [d.device_id for d in DeviceRegistry(tmp_path / "devices.json", clock=clock).list()] == [b.device_id]
    assert engine.authenticate(token_a) is None


def test_a_revoke_between_the_engines_read_and_write_is_kept(tmp_path):
    """The engine last read the file before the CLI revoked; its next write must not bring the device back."""
    clock = Clock()
    engine = DeviceRegistry(tmp_path / "devices.json", clock=clock)
    a, _ = engine.pair("Phone A", "ios")
    b, _ = engine.pair("Phone B", "android")
    DeviceRegistry(tmp_path / "devices.json", clock=clock).revoke(a.device_id)
    assert engine.rotate(b.device_id)  # a write that starts from the engine's stale view
    assert [d.device_id for d in DeviceRegistry(tmp_path / "devices.json", clock=clock).list()] == [b.device_id]


# ---------------------------------------------------------------------------- /v1/status


def test_status_for_the_desktop_helper(settings):
    with lan(settings) as c:
        clock = c.app.state.devices.clock = Clock()
        a, _ = pair(c, "Phone A"), pair(c, "Phone B")
        clock.t += 3600
        c.get("/v1/devices/me", headers=bearer(a["token"]))
        jobs = c.app.state.jobs
        for i, status in enumerate(["running", "queued", "queued", "succeeded"]):
            jobs.jobs[f"j{i}"] = Job(f"j{i}", "test", None, None, Path("x.wav"), {}, status=status)
        jobs.jobs["j2"].cancel.set()  # cancelled while queued: not waiting any more
        assert c.get("/v1/status", headers=bearer(a["token"])).status_code == 403
        with as_owner(c):
            st = c.get("/v1/status").json()
        assert st == {"server_id": a["server_id"], "server_name": a["server_name"], "version": st["version"],
                      "online_devices": 1, "paired_devices": 2, "pairing_open": True,
                      "jobs_running": 1, "jobs_queued": 1}
        c.app.state.pairing.close()
        with as_owner(c):
            assert c.get("/v1/status").json()["pairing_open"] is False


# ---------------------------------------------------------------------------- server name


def test_server_name_override_is_used_everywhere(settings, monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_COMPUTER_NAME", "ignored")
    monkeypatch.setenv("BRASSCRIBE_SERVER_NAME", "Brasscribe on Band room")
    with lan(settings) as c:
        c.app.state.hosts = ["192.0.2.20:8765"]
        assert c.get("/v1/health").json()["server_name"] == "Brasscribe on Band room"
        p = pair(c)
        assert p["server_name"] == "Brasscribe on Band room"
        with as_owner(c):
            st = c.get("/v1/pairing").json()
            assert c.get("/v1/status").json()["server_name"] == "Brasscribe on Band room"
        assert st["server_name"] == "Brasscribe on Band room"
        assert parse_qs(urlsplit(st["uri"]).query)["name"] == ["Brasscribe on Band room"]
    info = discovery.service_info(8765, ["192.0.2.20"])
    assert info.name == "Brasscribe on Band room._brasscribe._tcp.local."
    assert info.decoded_properties["host"] == "Band room"


def test_server_name_override_without_the_prefix_is_taken_whole(monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_SERVER_NAME", "Korpsets.maskin")
    assert discovery.server_names() == ("Korpsets maskin", "Korpsets maskin")


def test_the_operating_systems_computer_name_comes_before_the_host_name(monkeypatch):
    monkeypatch.delenv("BRASSCRIBE_COMPUTER_NAME", raising=False)
    monkeypatch.delenv("BRASSCRIBE_SERVER_NAME", raising=False)
    monkeypatch.setattr(discovery, "os_computer_name", lambda: "Kari's MacBook Pro")
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "Karis-MBP.local")
    assert discovery.server_names() == ("Brasscribe on Kari's MacBook Pro", "Kari's MacBook Pro")
    monkeypatch.setattr(discovery, "os_computer_name", lambda: None)
    assert discovery.service_name() == "Brasscribe on Karis-MBP"


@pytest.mark.skipif(sys.platform != "darwin", reason="scutil is macOS only")
def test_os_computer_name_reads_scutil_on_macos(monkeypatch):
    real = REAL_OS_COMPUTER_NAME
    monkeypatch.setattr(discovery.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Kari's MacBook Pro\n", ""))
    assert real() == "Kari's MacBook Pro"
    monkeypatch.setattr(discovery.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "err"))
    assert real() is None


# ---------------------------------------------------------------------------- local trust


def test_local_trust_can_be_turned_off(settings, monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_TRUST_LOCAL", "0")
    with TestClient(create_app(Settings(data_dir=settings.data_dir, adapters_dir=settings.adapters_dir))) as c:
        assert c.get("/v1/health").json()["auth_required"] is True
        assert c.get("/v1/jobs").status_code == 401
        assert c.get("/v1/devices").status_code == 403
        p = pair(c)
        assert c.get("/v1/jobs", headers=bearer(p["token"])).status_code == 200


def test_admin_token_is_required_for_management_while_configured(settings):
    s = Settings(data_dir=settings.data_dir, adapters_dir=settings.adapters_dir, admin_token=ADMIN, token="script")
    with TestClient(create_app(s)) as c:  # loopback, local trust on
        assert c.get("/v1/jobs").status_code == 200  # Studio still works
        for method, path in [("get", "/v1/status"), ("get", "/v1/devices"), ("get", "/v1/pairing"),
                             ("post", "/v1/pairing"), ("delete", "/v1/pairing"), ("get", "/v1/pairing/requests")]:
            assert getattr(c, method)(path).status_code == 403, path
            assert getattr(c, method)(path, headers=bearer("script")).status_code == 403, path
            assert getattr(c, method)(path, headers=bearer("wrong")).status_code == 403, path
            assert getattr(c, method)(path, headers=bearer(ADMIN)).status_code == 200, path
        c.app.state.pairing.open()
        p = pair(c)
        assert c.get("/v1/status", headers=bearer(p["token"])).status_code == 403
    s.trust_local = False
    with TestClient(create_app(s)) as c:  # remote access through a proxy: nothing is trusted by address
        assert c.get("/v1/jobs").status_code == 401
        assert c.get("/v1/jobs", headers=bearer(ADMIN)).status_code == 200
        assert c.delete(f"/v1/devices/{p['device_id']}", headers=bearer(ADMIN)).status_code == 204


def test_admin_token_file(settings, tmp_path, monkeypatch):
    path = tmp_path / "bandroom" / "admin-token"
    monkeypatch.setenv("BRASSCRIBE_ADMIN_TOKEN_FILE", str(path))
    s = Settings(data_dir=settings.data_dir, adapters_dir=settings.adapters_dir)
    token = s.admin_credential()
    assert token and path.read_text().strip() == token
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        path.chmod(0o644)
        with pytest.raises(PermissionError):
            s.admin_credential()
        path.chmod(0o600)
    with TestClient(create_app(s)) as c:
        assert c.get("/v1/status").status_code == 403
        assert c.get("/v1/status", headers=bearer(token)).status_code == 200


def test_no_admin_token_keeps_loopback_management(settings):
    with TestClient(create_app(settings)) as c:
        assert c.app.state.admin_token is None
        assert c.get("/v1/status").status_code == 200
