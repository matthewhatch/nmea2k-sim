import pytest
from nmea_sim.config import parse_config
from nmea_sim.transport import open_bus


def test_defaults(monkeypatch):
    monkeypatch.delenv('NMEA_CAN_CHANNEL', raising=False)
    monkeypatch.delenv('NMEA_SOURCE_ADDRESS', raising=False)
    assert parse_config([]).channel == 'vcan0'
    assert parse_config([]).source_address == 35


def test_precedence(monkeypatch):
    monkeypatch.setenv('NMEA_CAN_CHANNEL', 'vcan1')
    monkeypatch.setenv('NMEA_SOURCE_ADDRESS', '42')
    assert parse_config([]).channel == 'vcan1'
    assert parse_config([]).source_address == 42
    config = parse_config(['--channel', 'vcan2', '--source-address', '43'])
    assert (config.channel, config.source_address) == ('vcan2', 43)
    monkeypatch.setenv('NMEA_SOURCE_ADDRESS', 'invalid')
    assert parse_config(['--source-address', '1']).source_address == 1


@pytest.mark.parametrize('args', [['--channel', ''], ['--channel', '../can0'],
    ['--channel', 'x'*16], ['--source-address', '254'], ['--source-address', '-1'],
    ['--source-address', 'no'], ['--count', '0'], ['--timeout', 'nan'], ['--timeout', '0']])
def test_invalid(args):
    with pytest.raises(SystemExit):
        parse_config(args)


def test_guard_precedes_open(monkeypatch):
    monkeypatch.setattr('socket.if_nametoindex', lambda _: 3)
    monkeypatch.setattr('nmea_sim.transport.is_virtual_can', lambda _: False)
    monkeypatch.setattr('can.Bus', lambda **_: pytest.fail('must not open physical interface'))
    with pytest.raises(ValueError, match='allow-physical-tx'):
        open_bus(parse_config(['--channel', 'can0']), transmit=True)


def test_absent_interface(monkeypatch):
    def absent(_):
        raise OSError('missing')
    monkeypatch.setattr('socket.if_nametoindex', absent)
    with pytest.raises(ValueError, match='setup_vcan.sh'):
        open_bus(parse_config([]))


def test_rate_precedence(monkeypatch):
    monkeypatch.setenv('NMEA_RAPID_HZ', '10')
    monkeypatch.setenv('NMEA_DYNAMIC_HZ', '2')
    assert parse_config([]).rapid_hz == 10
    assert parse_config([]).dynamic_hz == 2
    config = parse_config(['--rapid-hz', '5', '--dynamic-hz', '1'])
    assert (config.rapid_hz, config.dynamic_hz) == (5, 1)
    monkeypatch.setenv('NMEA_RAPID_HZ', 'invalid')
    assert parse_config(['--rapid-hz', '5']).rapid_hz == 5


@pytest.mark.parametrize('option', ['--rapid-hz', '--dynamic-hz'])
@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', '101', 'invalid'])
def test_invalid_rates(option, value):
    with pytest.raises(SystemExit):
        parse_config([option, value])


@pytest.mark.parametrize('args', [['--manufacturer-code', '0'], ['--manufacturer-code', '2047'], ['--manufacturer-code', '2045'],
    ['--source-address', '252'], ['--source-address', '253'],
    ['--unique-number', '0'], ['--unique-number', '2097152'], ['--device-instance', '256'],
    ['--engine-instance', '253'], ['--system-instance', '16'], ['--device-key', '']])
def test_invalid_identity(args):
    with pytest.raises(SystemExit):
        parse_config(args)


def test_identity_config_and_stability(monkeypatch):
    from nmea_sim.config import stable_unique_number
    monkeypatch.setenv('NMEA_DEVICE_INSTANCE', '8')
    assert parse_config([]).device_instance == 8
    assert parse_config(['--device-instance', '2']).device_instance == 2
    monkeypatch.setattr('pathlib.Path.read_text', lambda _: 'host-id')
    default = parse_config([])
    assert stable_unique_number(default) == stable_unique_number(parse_config(['--source-address', '43']))
    assert stable_unique_number(default) != stable_unique_number(parse_config(['--device-key', 'engine-1']))
    assert stable_unique_number(parse_config(['--unique-number', '42'])) == 42
