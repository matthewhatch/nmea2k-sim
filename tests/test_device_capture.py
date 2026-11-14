import json
from pathlib import Path
import pytest
from nmea_sim.capture import read_candump
from nmea_sim.interop import validate_canboat
from nmea_sim.consumer import Decoder
from nmea_sim.can_id import extract

CAPTURES = Path(__file__).resolve().parents[1] / 'docs/captures'


def test_m3_independent_canboat_fixture():
    rows = [json.loads(line) for line in (CAPTURES / 'm3-device.canboat.jsonl').read_text().splitlines()]
    result = validate_canboat(read_candump(CAPTURES / 'm3-device.log'), rows)
    assert result['messages_compared'] > 50
    assert set(result['per_pgn']) == {59392, 59904, 60928, 126464, 126993, 126996, 126998, 127488, 127489}


def test_validator_detects_field_mismatch():
    rows = [json.loads(line) for line in (CAPTURES / 'm3-device.canboat.jsonl').read_text().splitlines()]
    row = next(row for row in rows if row.get('pgn') == 127488)
    row['fields']['Speed'] = 42
    with pytest.raises(ValueError, match='Speed'):
        validate_canboat(read_candump(CAPTURES / 'm3-device.log'), rows)


def test_capture_protocol_flow():
    frames = list(read_candump(CAPTURES / 'm3-device.log'))
    decoder = Decoder()
    decoded = []
    for frame in frames:
        state = decoder.receive(frame)
        if state is not None:
            decoded.append((frame, extract(frame.arbitration_id), state))
    claims = [(frame, state) for frame, info, state in decoded
              if info.pgn == 60928 and state.unique_number == 210]
    assert [extract(frame.arbitration_id).source for frame, _ in claims] == [210, 210, 210, 210, 211]
    first_claim = claims[0][0].timestamp
    first_engine = next(frame for frame, info, state in decoded if info.pgn == 127488)
    assert first_engine.timestamp - first_claim >= .24
    # The final two own claims are a winning reassertion and a losing relocation.
    for claim, _ in claims[-2:]:
        source = extract(claim.arbitration_id).source
        resumed = next(frame for frame, info, state in decoded
                       if info.pgn == 127488 and info.source == source and frame.timestamp > claim.timestamp)
        assert resumed.timestamp - claim.timestamp >= .24
    beats = [(frame, state) for frame, info, state in decoded if info.pgn == 126993]
    assert [state.sequence for _, state in beats] == [0, 1, 2, 3]
    assert beats[-1][0].timestamp - beats[-2][0].timestamp == pytest.approx(6, abs=.1)
    requests = [frame for frame in frames if extract(frame.arbitration_id).pgn == 59904]
    assert {extract(frame.arbitration_id).destination for frame in requests} >= {209, 210, 211, 255}
    nacks = [state.requested_pgn for _, info, state in decoded if info.pgn == 59392]
    assert nacks == [127508, 126993]
