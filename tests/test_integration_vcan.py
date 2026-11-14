"""Real SocketCAN integration: separate CLI processes, no virtual backend shortcut."""
import json
import os
import signal
import time
import shutil
import socket
import subprocess
import sys

import can
import pytest


@pytest.fixture
def vcan():
    try:
        socket.if_nametoindex('vcan0')
        bus = can.Bus(interface='socketcan', channel='vcan0')
    except (OSError, can.CanError) as exc:
        pytest.skip(f'vcan0 unavailable: {exc}; run sudo scripts/setup_vcan.sh with SocketCAN permissions')
    yield bus
    bus.shutdown()


def stop(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def read_records(path):
    # Ignore a final partial line while the receiver is writing.
    return [json.loads(line) for line in path.read_text().splitlines(keepends=True)
            if line.endswith('\n')]


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.01)
    pytest.fail('receiver output did not arrive before timeout')


def start_receiver(path, env=None):
    with path.open('w') as output:
        process = subprocess.Popen([sys.executable, '-m', 'nmea_sim.consumer', '--channel', 'vcan0'],
                                   stdout=output, stderr=subprocess.PIPE, text=True, env=env)
    try:
        wait_until(lambda: read_records(path))
        assert read_records(path)[0] == {'status': 'ready', 'channel': 'vcan0'}
    except BaseException:
        stop(process)
        raise
    return process


@pytest.mark.vcan
def test_independent_processes(vcan, tmp_path):
    # CLI overrides a poisoned channel env. A distinct source allows coexistence
    # with an operator's demo already running on vcan0.
    env = dict(os.environ, NMEA_CAN_CHANNEL='missing0')
    output = tmp_path / 'receiver.jsonl'
    receiver = start_receiver(output, env)
    simulator = None
    try:
        simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator', '--channel', 'vcan0',
            '--source-address', '201', '--unique-number', '201', '--count', '41'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env)
        _, stderr = simulator.communicate(timeout=15)
        assert simulator.returncode == 0, stderr
        def received():
            rows = [row for row in read_records(output) if row.get('source') == 201 and row.get('pgn') in (127488, 127489)]
            return rows if len(rows) >= 50 else None
        rows = wait_until(received)
        receiver.send_signal(signal.SIGINT)
        _, stderr = receiver.communicate(timeout=3)
        assert receiver.returncode == 0, stderr
        dynamic = [row for row in rows if row['pgn'] == 127489]
        records = [row for row in rows if row['pgn'] == 127488]
        assert len(records) == 41 and len(dynamic) == 9
        from nmea_sim.fast_packet import Reassembler
        from nmea_sim.pgn_127489 import decode
        assert all(record['oil_temperature_k'] is None for record in dynamic)
        assert all(record['active_status'] == [] for record in dynamic)
        frames = []
        while (frame := vcan.recv(.05)) is not None:
            if frame.arbitration_id in (0x09F200C9, 0x09F201C9):
                frames.append(frame)
        assert len(frames) == 77  # 41 rapid + 9 dynamic * 4 fragments
        dynamic_frames = [frame for frame in frames if frame.arbitration_id == 0x09F201C9]
        frames = [frame for frame in frames if frame.arbitration_id == 0x09F200C9]
        assert len(dynamic_frames) == 36
        reassembler = Reassembler()
        payloads = [payload for frame in dynamic_frames
                    if (payload := reassembler.feed(201, 127489, bytes(frame.data))) is not None]
        assert len(payloads) == 9
        from dataclasses import asdict
        for record, payload in zip(dynamic, payloads):
            for key, value in asdict(decode(payload)).items():
                assert record[key] == value
        assert [frame.data[0] >> 5 for frame in dynamic_frames[::4]] == [0,1,2,3,4,5,6,7,0]
        dynamic_duration = dynamic[-1]['timestamp'] - dynamic[0]['timestamp']
        assert 7.5 < dynamic_duration < 8.5
        assert dynamic[-1]['engine_hours'] > dynamic[0]['engine_hours']
        assert dynamic[-1]['coolant_temperature_k'] > dynamic[0]['coolant_temperature_k']
        start = records[0]['timestamp']
        from nmea_sim.engine_model import sample
        for record, frame in zip(records, frames):
            assert frame.is_extended_id and frame.arbitration_id == 0x09F200C9
            assert frame.dlc == 8 and bytes(frame.data)[6:] == b'\xff\xff'
            raw_rpm = int.from_bytes(frame.data[1:3], 'little') * .25
            raw_trim = int.from_bytes(frame.data[5:6], 'little', signed=True)
            assert record['rpm'] == raw_rpm
            assert record['trim'] == raw_trim
            assert abs(record['rpm'] - sample(record['timestamp'] - start).rpm) < 5
        duration = records[-1]['timestamp'] - start
        assert 7.5 < duration < 8.5
        assert all(.15 < b['timestamp'] - a['timestamp'] < .25
                   for a, b in zip(records, records[1:]))
        assert records[-1]['rpm'] > records[0]['rpm'] + 500
    finally:
        stop(receiver)
        if simulator is not None:
            stop(simulator)


@pytest.mark.vcan
def test_candump_extended(vcan):
    executable = shutil.which('candump')
    if executable is None:
        pytest.skip('candump not installed: sudo apt install can-utils')
    process = subprocess.Popen([executable, '-n', '1', 'vcan0,09F200CB:1FFFFFFF'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # Send until candump has bound its socket; no fixed startup race.
        for _ in range(20):
            vcan.send(can.Message(arbitration_id=0x09F200CB, is_extended_id=True,
                                 data=bytes.fromhex('00 e0 2e ff ff fc ff ff')))
            try:
                stdout, stderr = process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            pytest.fail('candump did not receive frame')
        assert process.returncode == 0, stderr
        assert '09F200CB' in stdout and '00 E0 2E FF FF FC FF FF' in stdout
    finally:
        stop(process)


@pytest.mark.vcan
def test_receiver_survives_damaged_dynamic_packets(vcan, tmp_path):
    from nmea_sim.fast_packet import fragment
    from nmea_sim.pgn_127489 import encode, DynamicUpdate
    output = tmp_path / 'damaged.jsonl'
    receiver = start_receiver(output)
    try:
        def send(data):
            vcan.send(can.Message(arbitration_id=0x09F201CA, is_extended_id=True, data=data))
        frames = fragment(encode(DynamicUpdate(engine_hours=123)), 0)
        for index in (0, 2, 3):
            send(frames[index])
        for frame in fragment(bytes(25), 1):
            send(frame)
        for frame in fragment(encode(DynamicUpdate(engine_hours=456)), 2):
            send(frame)
        def received():
            rows = [row for row in read_records(output) if row.get('source') == 202]
            return rows if rows else None
        records = wait_until(received)
        receiver.send_signal(signal.SIGINT)
        _, stderr = receiver.communicate(timeout=3)
        assert receiver.returncode == 0, stderr
        assert len(records) == 1 and records[0]['engine_hours'] == 456
        assert 'Ignoring malformed frame' in stderr
    finally:
        stop(receiver)


@pytest.mark.vcan
def test_device_claim_discovery_and_live_conflict(vcan, tmp_path):
    from nmea_sim import device_protocol as p
    from nmea_sim.can_id import compose, extract
    output = tmp_path / 'device.jsonl'
    receiver = start_receiver(output)
    simulator = None
    try:
        simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator', '--channel', 'vcan0',
            '--source-address', '215', '--unique-number', '215', '--device-instance', '9',
            '--engine-instance', '3', '--count', '16'], stderr=subprocess.PIPE, text=True)
        def rows(pgn, source=215):
            return [r for r in read_records(output) if r.get('pgn') == pgn and r.get('source') == source]
        claim = wait_until(lambda: rows(p.CLAIM))[0]
        rapid = wait_until(lambda: rows(127488))[0]
        assert rapid['timestamp'] - claim['timestamp'] >= .24
        assert rapid['instance'] == 3 and claim['device_instance'] == 9
        def send(pgn, payload, source=219, destination=255):
            vcan.send(can.Message(arbitration_id=compose(pgn, source, 6, destination),
                                 data=payload, is_extended_id=True))
        for pgn in (p.PRODUCT, p.CONFIGURATION, p.PGN_LIST):
            send(p.REQUEST, p.encode_request(pgn), destination=215)
            wait_until(lambda: rows(pgn))
        product = rows(p.PRODUCT)[0]
        assert product['model_id'] == 'NMEA Engine Sim TEST'
        assert product['certification_level'] is None
        send(p.REQUEST, p.encode_request(127508), destination=215)
        assert wait_until(lambda: rows(p.ACK))[0]['control'] == 1
        send(p.CLAIM, p.Name(1, 2046, device_instance=8).encode(), source=215)
        claim2 = wait_until(lambda: rows(p.CLAIM, 216))[0]
        rapid2 = wait_until(lambda: rows(127488, 216))[0]
        assert rapid2['timestamp'] - claim2['timestamp'] >= .24
        assert rapid2['instance'] == 3
        _, stderr = simulator.communicate(timeout=8)
        assert simulator.returncode == 0, stderr
        receiver.send_signal(signal.SIGINT)
        _, stderr = receiver.communicate(timeout=3)
        assert receiver.returncode == 0, stderr
    finally:
        stop(receiver)
        if simulator is not None:
            stop(simulator)
