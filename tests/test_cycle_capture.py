import hashlib
import json
from pathlib import Path
import pytest
from nmea_sim.capture import read_candump
from nmea_sim.interop import validate_canboat
from nmea_sim.consumer import Decoder
from nmea_sim.can_id import extract
from nmea_sim.engine_model import state_at

CAPTURES = Path(__file__).resolve().parents[1] / 'docs/captures'


def test_full_cycle_independent_decode_and_provenance():
    capture = CAPTURES / 'm4-cycle.log'
    decoded = CAPTURES / 'm4-cycle.canboat.jsonl'
    report = json.loads((CAPTURES / 'm4-cycle.canboat.validation.json').read_text())
    rows = [json.loads(line) for line in decoded.read_text().splitlines()]
    result = validate_canboat(read_candump(capture), rows, 'cycle')
    assert result['messages_compared'] == 308
    assert result['per_pgn'] == {127488: 256, 127489: 52}
    assert result['engine_ranges']['rpm'] == {'min': 0, 'max': 4500}
    assert result['engine_ranges']['fuel_rate_lph'] == {'min': 0, 'max': 35}
    assert report['capture_sha256'] == hashlib.sha256(capture.read_bytes()).hexdigest()
    assert report['decoded_sha256'] == hashlib.sha256(decoded.read_bytes()).hexdigest()
    assert report['canboat_revision'] == '2a42e004e01094b25049dddf737277f33c324ff1'
    assert report['messages_compared'] == result['messages_compared']


def test_full_cycle_phases_timing_and_stopped_hours():
    decoder = Decoder()
    rapid, dynamic = [], []
    frames = list(read_candump(CAPTURES / 'm4-cycle.log'))
    assert len(frames) == 464
    for frame in frames:
        info = extract(frame.arbitration_id)
        assert info.source == 230 and info.priority == 2
        state = decoder.receive(frame)
        if state is not None:
            assert state.instance == 1
            (rapid if info.pgn == 127488 else dynamic).append((frame.timestamp, state))
    start = rapid[0][0]
    assert rapid[-1][0] - start == pytest.approx(51, abs=.5)
    assert {state_at(max(0, t-start)).phase.value for t, _ in rapid} == {
        'off', 'starting', 'idle', 'acceleration', 'cruise', 'deceleration'}
    assert all(.15 < b[0] - a[0] < .25 for a, b in zip(rapid, rapid[1:]))
    assert all(.9 < b[0] - a[0] < 1.1 for a, b in zip(dynamic, dynamic[1:]))
    assert rapid[-1][1].rpm == 0
    stopped = [state for t, state in dynamic if 47 < t-start < 51]
    assert len(stopped) >= 3
    assert all(state.fuel_rate_lph == 0 and state.oil_pressure_pa == 0 for state in stopped)
    assert len({state.engine_hours for state in stopped}) == 1
    assert stopped[0].engine_hours == pytest.approx(100 + 44/3600)


def test_independent_dynamic_mismatch_is_detected():
    rows = [json.loads(line) for line in (CAPTURES / 'm4-cycle.canboat.jsonl').read_text().splitlines()]
    row = next(r for r in rows if r.get('pgn') == 127489)
    row['fields']['Alternator Potential'] = 99
    with pytest.raises(ValueError, match='Alternator Potential'):
        validate_canboat(read_candump(CAPTURES / 'm4-cycle.log'), rows, 'cycle')
