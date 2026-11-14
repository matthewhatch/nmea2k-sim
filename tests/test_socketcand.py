"""Protocol fixtures exercise TCP fragmentation; real gateway tests are separate."""
import socket
import threading
import time
from dataclasses import replace
import pytest
from nmea_sim.dashboard_config import DashboardConfig, parse_dashboard_config
from nmea_sim.receive_transport import SocketcandTransport, parse_frame


def test_remote_configuration(monkeypatch):
    for name in ('NMEA_TRANSPORT', 'NMEA_GATEWAY_HOST', 'NMEA_GATEWAY_PORT', 'NMEA_CAN_CHANNEL'):
        monkeypatch.delenv(name, raising=False)
    assert parse_dashboard_config([]) == DashboardConfig()
    monkeypatch.setenv('NMEA_TRANSPORT', 'socketcand')
    monkeypatch.setenv('NMEA_GATEWAY_HOST', 'gateway')
    monkeypatch.setenv('NMEA_GATEWAY_PORT', '1234')
    monkeypatch.setenv('NMEA_CAN_CHANNEL', 'can0')
    config = parse_dashboard_config([])
    assert (config.transport, config.host, config.port, config.channel) == ('socketcand', 'gateway', 1234, 'can0')
    config = parse_dashboard_config(['--transport', 'socketcan', '--host', 'other', '--port', '29536', '--channel', 'vcan0'])
    assert (config.transport, config.host, config.port, config.channel) == ('socketcan', 'other', 29536, 'vcan0')


@pytest.mark.parametrize('args', [['--transport','other'], ['--transport','socketcand'], ['--port','0'], ['--port','65536']])
def test_invalid_configuration(args):
    with pytest.raises(SystemExit):
        parse_dashboard_config(args)


@pytest.mark.parametrize('identifier,extended', [('1FFFFFFF', True), ('00000123', True), ('123', False)])
def test_frame_identity_payload_metadata(identifier, extended):
    frame = parse_frame(f'< frame {identifier} 123.456789 0001FEFF >'.encode(), 'can0')
    assert frame.arbitration_id == int(identifier, 16) and frame.is_extended_id == extended
    assert frame.timestamp == 123.456789 and frame.channel == 'can0'
    assert frame.dlc == 4 and bytes(frame.data) == b'\x00\x01\xfe\xff'
    assert not hasattr(SocketcandTransport, 'send')
    assert parse_frame(b'< frame 123 0.0  >', 'vcan0').dlc == 0


@pytest.mark.parametrize('record', [b'< frame 20000000 1.0 00 >', b'< frame FFF 1.0 00 >',
    b'< frame 09F20023 nan 00 >', b'< frame 09F20023 1.0 0 >',
    b'< frame 09F20023 1.0 000000000000000000 >', b'< frame 09F20023 1.0 ZZ >',
    b'< frame 09F20023 1.0 00', b'< unexpected >'])
def test_invalid_frames(record):
    with pytest.raises(ValueError):
        parse_frame(record, 'vcan0')


@pytest.fixture
def server():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(2)
    errors = []
    threads = []
    def start(action):
        def run():
            try:
                with listener.accept()[0] as client:
                    client.settimeout(2)
                    action(client)
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        threads.append(thread)
    yield DashboardConfig(transport='socketcand', host='127.0.0.1', port=listener.getsockname()[1]), start
    listener.close()
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    assert not errors


def handshake(client):
    for part in (b'< h', b'i >'):
        client.sendall(part)
    assert client.recv(128) == b'< open vcan0 >'
    client.sendall(b'< ok >')
    assert client.recv(128) == b'< rawmode >'
    client.sendall(b'< ok >')


def test_fragmentation_coalescing_order_eof(server):
    config, start = server
    def action(client):
        handshake(client)
        client.sendall(b'< frame 09F20023 1.0 00')
        time.sleep(.01)
        client.sendall(b'01 >< frame 09F20123 2.0 FF >')
        assert client.recv(128) == b''  # no CAN writes, even during close
    start(action)
    transport = SocketcandTransport(config)
    try:
        frames = [transport.recv(1), transport.recv(1)]
        assert [f.arbitration_id for f in frames] == [0x09F20023, 0x09F20123]
        assert [bytes(f.data) for f in frames] == [b'\0\1', b'\xff']
        assert transport.recv(.01) is None
    finally:
        transport.close()


@pytest.mark.parametrize('data,exception', [(b'< frame 123 1.0 00', ConnectionError), (b'x'*129, ValueError)])
def test_truncation_and_bounded_input(server, data, exception):
    config, start = server
    def action(client):
        handshake(client)
        client.sendall(data)
    start(action)
    transport = SocketcandTransport(config)
    try:
        with pytest.raises(exception):
            transport.recv(1)
        assert len(transport.buffer) <= 4096
    finally:
        transport.close()


def test_wrong_handshake(server):
    config, start = server
    start(lambda client: client.sendall(b'< error >'))
    with pytest.raises(ValueError, match='handshake'):
        SocketcandTransport(config)
