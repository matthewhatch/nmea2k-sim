import pytest
from nmea_sim.fast_packet import fragment, Reassembler


@pytest.mark.parametrize('length', [1, 6, 7, 8, 13, 26, 222, 223])
@pytest.mark.parametrize('sequence', range(8))
def test_roundtrip(length, sequence):
    payload = bytes(range(length))
    frames = fragment(payload, sequence)
    rx = Reassembler()
    results = [rx.feed(35, 127489, frame) for frame in frames]
    assert results[-1] == payload
    assert all(result is None for result in results[:-1])
    assert rx.pending_count == 0
    assert all(len(frame) == 8 for frame in frames)
    assert [frame[0] for frame in frames] == [(sequence << 5) | i for i in range(len(frames))]


def test_known_headers_and_padding():
    frames = fragment(bytes(range(26)), 7)
    assert frames == [bytes.fromhex(value) for value in (
        'e0 1a 00 01 02 03 04 05', 'e1 06 07 08 09 0a 0b 0c',
        'e2 0d 0e 0f 10 11 12 13', 'e3 14 15 16 17 18 19 ff')]


@pytest.mark.parametrize('length,sequence', [(0, 0), (224, 0), (26, -1), (26, 8)])
def test_invalid_fragment(length, sequence):
    with pytest.raises(ValueError):
        fragment(bytes(length), sequence)


@pytest.mark.parametrize('order', [[1, 2, 3], [0, 2, 3], [0, 1, 1, 2, 3],
                                   [0, 0, 1, 2, 3], [0, 2, 1, 3], [0, 3, 1, 2]])
def test_loss_duplicate_reorder(order):
    frames = fragment(bytes(range(26)), 0)
    rx = Reassembler()
    assert all(rx.feed(35, 127489, frames[i]) is None for i in order)
    assert rx.pending_count == 0
    assert [rx.feed(35, 127489, frame) for frame in frames][-1] == bytes(range(26))


def test_timeout_absolute_and_recovery():
    now = [0.0]
    rx = Reassembler(timeout=.75, clock=lambda: now[0])
    frames = fragment(bytes(range(26)), 0)
    rx.feed(35, 127489, frames[0])
    now[0] = .5
    rx.feed(35, 127489, frames[1])
    now[0] = .75
    assert rx.feed(35, 127489, frames[2]) is None
    assert rx.feed(35, 127489, frames[3]) is None
    assert rx.pending_count == 0
    assert [rx.feed(35, 127489, frame) for frame in frames][-1] == bytes(range(26))


def test_idle_expiry():
    now = [0.0]
    rx = Reassembler(clock=lambda: now[0])
    rx.feed(35, 127489, fragment(bytes(26), 0)[0])
    now[0] = 1
    rx.expire()
    assert rx.pending_count == 0


def test_interleaved_sources_pgn_destination_sequence():
    rx = Reassembler()
    streams = [(35, 127489, None, 0), (36, 127489, None, 0),
               (35, 127490, None, 0), (35, 127489, None, 1), (35, 127489, 7, 0)]
    packets = [fragment(bytes([i])*26, key[3]) for i, key in enumerate(streams)]
    for counter in range(4):
        for i, (source, pgn, dest, _) in enumerate(streams):
            result = rx.feed(source, pgn, packets[i][counter], dest)
            assert result == (bytes([i])*26 if counter == 3 else None)


def test_bounded_eviction():
    now = [0.0]
    rx = Reassembler(max_packets=2, clock=lambda: now[0])
    frames = fragment(bytes(26), 0)
    for source in (1, 2, 3):
        rx.feed(source, 127489, frames[0])
        now[0] += .1
    assert rx.pending_count == 2
    assert all(rx.feed(1, 127489, frame) is None for frame in frames[1:])
    assert [rx.feed(2, 127489, frame) for frame in frames[1:]][-1] == bytes(26)


@pytest.mark.parametrize('bad', [b'', b'\x00', b'\x00\x00' + bytes(6),
    b'\x00\xe0' + bytes(6), b'\x00\x1a' + bytes(5), bytes(9)])
def test_malformed_start(bad):
    rx = Reassembler()
    assert rx.feed(35, 127489, bad) is None
    assert rx.pending_count == 0


@pytest.mark.parametrize('bad', [b'\x01', b'\x01\x00', b'\x01' + bytes(8)])
def test_malformed_continuation(bad):
    rx = Reassembler()
    frames = fragment(bytes(26), 0)
    rx.feed(35, 127489, frames[0])
    assert rx.feed(35, 127489, bad) is None
    assert rx.pending_count == 0


def test_short_final_and_sequence_rollover():
    rx = Reassembler()
    for sequence in (6, 7, 0, 1):
        frames = fragment(bytes(26), sequence)
        frames[-1] = frames[-1][:-1]  # final padding may be omitted
        assert [rx.feed(35, 127489, frame) for frame in frames][-1] == bytes(26)


@pytest.mark.parametrize('kwargs', [{'timeout': 0}, {'timeout': float('nan')}, {'max_packets': 0}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        Reassembler(**kwargs)


def test_diagnostic_reassembly_error_counters():
    now = [0.0]
    receiver = Reassembler(clock=lambda: now[0])
    frames = fragment(bytes(26), 0)
    receiver.feed(35, 127489, frames[1])
    receiver.feed(35, 127489, frames[0])
    receiver.feed(35, 127489, frames[2])
    receiver.feed(35, 127489, frames[0])
    now[0] = 1
    receiver.expire()
    assert receiver.error_counts == {'orphan_frame': 1, 'unexpected_counter': 1, 'timeout': 1}
    snapshot = receiver.error_counts
    snapshot['timeout'] = 999
    assert receiver.error_counts['timeout'] == 1
