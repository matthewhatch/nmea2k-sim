import json
import subprocess
from types import SimpleNamespace
import pytest
from nmea_sim.config import Config
from nmea_sim.transport import open_bus, is_virtual_can


@pytest.mark.parametrize('name,kind,allowed', [('vcan0', 'can', False),
    ('bench0', 'vcan', True), ('vcan0', 'vcan', True), ('vcan_fake', None, False)])
def test_kernel_type_not_name(monkeypatch, name, kind, allowed):
    monkeypatch.setattr('socket.if_nametoindex', lambda _: 3)
    def run(command, **kwargs):
        assert command == ['ip', '-json', '-details', 'link', 'show', 'dev', name]
        return SimpleNamespace(stdout=json.dumps([{'ifname': name, 'linkinfo': {'info_kind': kind}}]))
    monkeypatch.setattr('subprocess.run', run)
    bus = object()
    opened = []
    monkeypatch.setattr('can.Bus', lambda **kwargs: opened.append(kwargs) or bus)
    if allowed:
        assert open_bus(Config(name, 35), transmit=True) is bus
        assert len(opened) == 1
    else:
        with pytest.raises(ValueError, match='allow-physical-tx'):
            open_bus(Config(name, 35), transmit=True)
        assert not opened


@pytest.mark.parametrize('error', [FileNotFoundError(), subprocess.TimeoutExpired('ip', 3),
                                  subprocess.CalledProcessError(1, 'ip')])
def test_unknown_type_fails_closed(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr('subprocess.run', fail)
    with pytest.raises(ValueError, match='Transmission refused'):
        is_virtual_can('vcan0')


def test_invalid_type_response(monkeypatch):
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: SimpleNamespace(stdout='invalid json'))
    with pytest.raises(ValueError, match='Transmission refused'):
        is_virtual_can('vcan0')


@pytest.mark.parametrize('transmit,opt_in', [(False, False), (True, True)])
def test_rx_and_explicit_optin_skip_type_guard(monkeypatch, transmit, opt_in):
    monkeypatch.setattr('socket.if_nametoindex', lambda _: 3)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('must not inspect type'))
    marker = object()
    monkeypatch.setattr('can.Bus', lambda **kwargs: marker)
    assert open_bus(Config('can0', 35, allow_physical_tx=opt_in, manufacturer_code=123), transmit=transmit) is marker


def test_test_identity_blocked_even_with_physical_optin(monkeypatch):
    monkeypatch.setattr('socket.if_nametoindex', lambda _: 3)
    monkeypatch.setattr('nmea_sim.transport.is_virtual_can', lambda _: False)
    monkeypatch.setattr('can.Bus', lambda **kw: pytest.fail('must not transmit test identity on hardware'))
    with pytest.raises(ValueError, match='2046'):
        open_bus(Config('can0', 35, allow_physical_tx=True), transmit=True)


def test_assigned_identity_still_requires_optin(monkeypatch):
    monkeypatch.setattr('socket.if_nametoindex', lambda _: 3)
    monkeypatch.setattr('nmea_sim.transport.is_virtual_can', lambda _: False)
    monkeypatch.setattr('can.Bus', lambda **kw: pytest.fail('must not open physical TX without opt-in'))
    with pytest.raises(ValueError, match='allow-physical-tx'):
        open_bus(Config('can0', 35, manufacturer_code=123), transmit=True)
