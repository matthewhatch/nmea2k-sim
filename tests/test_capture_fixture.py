"""Offline replay of a real candump capture, without a SocketCAN dependency."""
from pathlib import Path
import re
import can
import pytest
from nmea_sim.consumer import Decoder
from nmea_sim.can_id import extract
from nmea_sim.engine_model import sample

CAPTURE = Path(__file__).resolve().parents[1] / 'docs/captures/engine-default.log'


def frames():
    for line in CAPTURE.read_text().splitlines():
        match = re.fullmatch(r'\(([0-9.]+)\) vcan0 ([0-9A-F]{8})#([0-9A-F]{16})', line)
        assert match, line
        timestamp, identifier, data = match.groups()
        yield can.Message(timestamp=float(timestamp), arbitration_id=int(identifier, 16),
                          is_extended_id=True, data=bytes.fromhex(data))


def test_recorded_capture_replay():
    wire = list(frames())
    assert len(wire) == 113
    decoder = Decoder()
    rapid, dynamic = [], []
    for frame in wire:
        identifier = extract(frame.arbitration_id)
        assert identifier.source == 205 and identifier.priority == 2
        state = decoder.receive(frame)
        if identifier.pgn == 127488:
            rapid.append((frame, state))
        elif state is not None:
            dynamic.append((frame, state))
    assert len(rapid) == 61 and len(dynamic) == 13
    assert rapid[0][1].rpm == 0
    assert rapid[-1][1].rpm == pytest.approx(1560, abs=5)
    assert dynamic[0][1].engine_hours == 100
    assert dynamic[-1][1].engine_hours == pytest.approx(100 + 10/3600)
    assert dynamic[0][1].fuel_rate_lph == 0
    assert dynamic[0][1].alternator_voltage_v == 12.6
    assert dynamic[-1][1].alternator_voltage_v == pytest.approx(14.2)
    assert all(state.oil_temperature_k is None and state.coolant_pressure_pa is None
               and state.fuel_pressure_pa is None and state.engine_load_pct is None
               and state.engine_torque_pct is None for _, state in dynamic)
    start = rapid[0][0].timestamp
    for frame, state in rapid:
        # Cross-check against independently read wire offsets, not encode().
        assert state.rpm == int.from_bytes(frame.data[1:3], 'little') * .25
        assert state.trim == int.from_bytes(frame.data[5:6], 'little', signed=True)
        assert state.boost_pa is None
        assert frame.data[3:5] == b'\xff\xff' and frame.data[6:] == b'\xff\xff'
        assert abs(state.rpm - sample(frame.timestamp - start).rpm) < 5
    intervals = [b[0].timestamp - a[0].timestamp for a, b in zip(rapid, rapid[1:])]
    assert all(.15 <= interval <= .25 for interval in intervals)
    assert rapid[-1][0].timestamp - start == pytest.approx(12, abs=.5)
    assert decoder.reassembler.pending_count == 0
