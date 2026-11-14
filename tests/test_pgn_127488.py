import pytest
import can
from nmea_sim.pgn_127488 import RapidUpdate, encode, decode
from nmea_sim.receiver import receive_frame
from nmea_sim.can_id import compose


def test_known_vector():
    # 3000 RPM / .25 = 12000 = 0x2ee0; signed -4 = 0xfc.
    vector = bytes.fromhex('00 e0 2e ff ff fc ff ff')
    state = RapidUpdate(0, 3000, None, -4)
    assert encode(state) == vector
    assert decode(vector) == state


@pytest.mark.parametrize('rpm,trim', [(0, -128), (750.13, -4), (4500, 12), (16383, 124)])
def test_resolution(rpm, trim):
    actual = decode(encode(RapidUpdate(0, rpm, 120000, trim)))
    assert abs(actual.rpm - rpm) <= .125
    assert actual.trim == trim
    assert actual.boost_pa == 120000


@pytest.mark.parametrize('word,byte', [(65535, 127), (65534, 126), (65533, 125)])
def test_sentinels(word, byte):
    import struct
    assert decode(struct.pack('<BHHbH', 255, word, word, byte, 65535)) == RapidUpdate(None, None, None, None)


def test_all_unavailable():
    assert encode(RapidUpdate(None, None, None, None)) == bytes.fromhex('ff ff ff ff ff 7f ff ff')


@pytest.mark.parametrize('state', [RapidUpdate(0, -1, None, 0), RapidUpdate(0, float('nan'), None, 0),
    RapidUpdate(0, 16383.25, None, 0), RapidUpdate(0, 0, None, 125), RapidUpdate(253, 0, None, 0)])
def test_invalid_fields(state):
    with pytest.raises(ValueError):
        encode(state)


@pytest.mark.parametrize('length', [0, 6, 7, 9])
def test_wrong_length(length):
    with pytest.raises(ValueError):
        decode(bytes(length))


@pytest.mark.parametrize('kwargs', [{'is_extended_id': False}, {'is_remote_frame': True},
    {'is_error_frame': True}, {'is_fd': True}, {'arbitration_id': compose(127489)}])
def test_ignore_frames(kwargs):
    args = dict(arbitration_id=compose(127488), is_extended_id=True, data=bytes(8))
    args.update(kwargs)
    assert receive_frame(can.Message(**args)) is None


def test_receiver_rejects_malformed():
    with pytest.raises(ValueError):
        receive_frame(can.Message(arbitration_id=compose(127488), is_extended_id=True, data=bytes(7)))
