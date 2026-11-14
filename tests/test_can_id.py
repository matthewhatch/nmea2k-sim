import pytest
from nmea_sim.can_id import compose, extract


@pytest.mark.parametrize('pgn', [0, 59904, 60928, 127488, 0x1EF00, 0x2F001, 0x3FFFF])
@pytest.mark.parametrize('source', [0, 35, 255])
@pytest.mark.parametrize('priority', [0, 2, 7])
def test_roundtrip(pgn, source, priority):
    result = extract(compose(pgn, source, priority, 17))
    assert (result.pgn, result.source, result.priority) == (pgn, source, priority)
    assert result.destination == (17 if (pgn >> 8) & 255 < 240 else None)


def test_known_id():
    assert compose(127488) == 0x09F20023
    assert compose(59904, destination=35, priority=6) == 0x18EA2323


@pytest.mark.parametrize('kwargs', [{'pgn': -1}, {'pgn': 0x40000}, {'pgn': 59905},
    {'pgn': 127488, 'priority': 8}, {'pgn': 127488, 'source': 256},
    {'pgn': 59904, 'destination': -1}])
def test_invalid(kwargs):
    with pytest.raises(ValueError):
        compose(**kwargs)


@pytest.mark.parametrize('value', [-1, 0x20000000])
def test_invalid_extract(value):
    with pytest.raises(ValueError):
        extract(value)
