import pytest

from brasscribe_engine import __version__, discovery


@pytest.mark.slow
def test_service_info_advertises_port_addresses_and_pairing_hint():
    info = discovery.service_info(8765, ["192.0.2.20", "198.51.100.5"], hostname="studio-mac.local")
    assert info.type == "_brasscribe._tcp.local."
    assert info.name == "Brasscribe on studio-mac._brasscribe._tcp.local."
    assert info.server == "studio-mac.local."
    assert info.port == 8765
    assert sorted(info.parsed_addresses()) == ["192.0.2.20", "198.51.100.5"]
    assert info.decoded_properties == {"v": __version__, "api": "/v1", "auth": "pair", "host": "studio-mac"}


def test_advertise_without_addresses_is_a_no_op():
    with discovery.advertise(8765, []) as name:
        assert name is None


def test_lan_only_drops_vpn_addresses_unless_nothing_else_is_left():
    assert discovery.lan_only(["100.64.0.1", "192.0.2.95"]) == ["192.0.2.95"]
    assert discovery.lan_only(["100.64.0.2"]) == ["100.64.0.2"]


def test_service_info_carries_the_stable_server_id():
    info = discovery.service_info(9000, ["192.0.2.20"], hostname="studio-mac", server_id="ab" * 16)
    assert info.decoded_properties["id"] == "ab" * 16


def test_the_desktop_helper_names_the_computer(monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_COMPUTER_NAME", "Karis MacBook\n")
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "Karis-MacBook-Pro.local")
    info = discovery.service_info(8765, ["192.0.2.20"], server_id="ab" * 16)
    assert info.name == "Brasscribe on Karis MacBook._brasscribe._tcp.local."
    assert info.server == "Karis-MacBook-Pro.local."
    assert info.decoded_properties["host"] == "Karis MacBook"
    assert discovery.service_name() == "Brasscribe on Karis MacBook"


def test_computer_name_fits_one_dns_label(monkeypatch):
    monkeypatch.setenv("BRASSCRIBE_COMPUTER_NAME", "Bjørnstjerne's " + "å" * 60)
    name = discovery.service_name()
    assert len(name.encode()) <= 63 and name.startswith("Brasscribe on Bjørnstjerne's å")
    monkeypatch.setenv("BRASSCRIBE_COMPUTER_NAME", "   ")
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "studio-mac")
    assert discovery.service_name() == "Brasscribe on studio-mac"


def test_server_name_in_health_matches_the_advertised_name(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from brasscribe_engine.api import create_app

    monkeypatch.setenv("BRASSCRIBE_COMPUTER_NAME", "Karis MacBook")
    with TestClient(create_app(settings)) as c:
        assert c.get("/v1/health").json()["server_name"] == "Brasscribe on Karis MacBook"
