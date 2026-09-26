from brasscribe_engine import __version__, discovery


def test_service_info_advertises_port_addresses_and_pairing_hint():
    info = discovery.service_info(8765, ["192.168.1.20", "10.0.0.5"], hostname="studio-mac.local")
    assert info.type == "_brasscribe._tcp.local."
    assert info.name == "Brasscribe on studio-mac._brasscribe._tcp.local."
    assert info.server == "studio-mac.local."
    assert info.port == 8765
    assert sorted(info.parsed_addresses()) == ["10.0.0.5", "192.168.1.20"]
    assert info.decoded_properties == {"v": __version__, "api": "/v1", "auth": "pair"}


def test_advertise_without_addresses_is_a_no_op():
    with discovery.advertise(8765, []) as name:
        assert name is None


def test_lan_only_drops_vpn_addresses_unless_nothing_else_is_left():
    assert discovery.lan_only(["100.64.0.1", "192.168.10.95"]) == ["192.168.10.95"]
    assert discovery.lan_only(["100.101.1.2"]) == ["100.101.1.2"]
