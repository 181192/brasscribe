"""Requests from web pages of other sites, and Host names a client on this computer may use."""

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import guard
from brasscribe_engine.api import create_app

from .test_companion import lan

OTHER_SITE = "http://example.com"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def local(settings):
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as c:
        yield c


def test_a_page_of_another_site_cannot_change_anything(local, audio):
    c = local
    request_id = c.app.state.pair_requests.create("Phone", "android").request_id
    for headers in ({"Origin": OTHER_SITE, **FORM}, {"Origin": "null", **FORM},
                    {"Sec-Fetch-Site": "cross-site", **FORM}, {"Sec-Fetch-Site": "same-site", **FORM}):
        assert c.post("/v1/pairing", content=b"", headers=headers).status_code == 403
        assert c.post(f"/v1/pairing/requests/{request_id}/approve", content=b"", headers=headers).status_code == 403
        r = c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes())}, headers={
            k: v for k, v in headers.items() if k != "Content-Type"})
        assert r.status_code == 403
        assert c.delete("/v1/pairing", headers=headers).status_code == 403
    assert [r.request_id for r in c.app.state.pair_requests.pending()] == [request_id]
    assert not any(c.app.state.settings.uploads_dir.iterdir())
    # reads are not state-changing; the browser keeps their answers from the other site
    assert c.get("/v1/health", headers={"Origin": OTHER_SITE}).status_code == 200


def test_a_page_under_another_host_name_is_refused(local):
    c = local
    headers = {"Host": "brasscribe.example.com:8765", "Origin": "http://brasscribe.example.com:8765"}
    assert c.get("/v1/jobs", headers=headers).status_code == 400
    assert c.get("/v1/pairing", headers=headers).status_code == 400
    assert c.post("/v1/pairing", json={}, headers=headers).status_code == 400
    assert c.get("/", headers=headers).status_code == 400


def test_studio_and_native_clients_still_work(local, audio):
    c = local
    for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "Studio-Mac.local:8765", "studio-mac.local.",
                 "192.0.2.10:8765", "10.0.2.2:8765", "[2001:db8::1]:8765", "testserver"):
        assert c.get("/v1/health", headers={"Host": host}).status_code == 200, host
    same = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}
    assert c.post("/v1/pairing", json={}, headers=same).status_code == 200
    assert c.post("/v1/audio", files={"file": ("song.wav", audio.read_bytes())}, headers=same).status_code == 201
    assert c.post("/v1/pairing", json={}).status_code == 200  # a native client: no Origin, no Sec-Fetch-*
    assert c.post("/v1/pairing", json={}, headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_a_proxy_host_name_can_be_allowed(settings, monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_ALLOWED_HOSTS", "engine.example.net, other.example.net")
    s = type(settings)(data_dir=settings.data_dir, adapters_dir=settings.adapters_dir, gpu_lock=settings.gpu_lock)
    with TestClient(create_app(s), client=("127.0.0.1", 50000)) as c:
        assert c.get("/v1/health", headers={"Host": "engine.example.net"}).status_code == 200
        assert c.get("/v1/health", headers={"Host": "Other.Example.Net:443"}).status_code == 200
        assert c.get("/v1/health", headers={"Host": "third.example.net"}).status_code == 400


def test_host_names_of_lan_clients_are_not_checked(settings):
    with lan(settings) as c:  # not trusted by address: they need a token anyway
        assert c.get("/v1/health", headers={"Host": "studio-mac.example.net"}).status_code == 200
        assert c.get("/v1/jobs", headers={"Host": "studio-mac.example.net"}).status_code == 401


@pytest.mark.parametrize("host, name", [("127.0.0.1:8765", "127.0.0.1"), ("[::1]:8765", "::1"), ("::1", "::1"),
                                        ("Mac.Local.:80", "mac.local"), ("localhost", "localhost")])
def test_host_name(host, name):
    assert guard.host_name(host) == name


@pytest.mark.parametrize("origin, host, same", [
    ("http://127.0.0.1:8765", "127.0.0.1:8765", True), ("http://localhost", "localhost:80", True),
    ("https://engine.example.net", "engine.example.net", True), ("http://127.0.0.1:8766", "127.0.0.1:8765", False),
    ("http://example.com", "127.0.0.1:8765", False), ("null", "127.0.0.1:8765", False),
    ("file://", "127.0.0.1:8765", False)])
def test_same_origin(origin, host, same):
    assert guard.same_origin(origin, host) is same
