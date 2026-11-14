from dataclasses import replace, fields
import struct
import can
import pytest
from nmea_sim.pgn_127489 import DynamicUpdate, Status1, Status2, active_status, encode, decode
from nmea_sim.fast_packet import fragment, Reassembler
from nmea_sim.receiver import Decoder
from nmea_sim.can_id import compose
from nmea_sim.engine_model import sample_dynamic

# Independently calculated from the documented offsets/resolutions:
# oil=250000/100=2500, coolant=353.15/.01=35315,
# volts=14.2/.01=1420, fuel=12.3/.1=123, hours=100*3600=360000.
VECTOR = bytes.fromhex('00 c4 09 ff ff f3 89 8c 05 7b 00 40 7e 05 00 ff ff ff ff ff 22 00 01 00 7f 7f')
STATE = DynamicUpdate(oil_pressure_pa=250000, coolant_temperature_k=353.15,
    alternator_voltage_v=14.2, fuel_rate_lph=12.3, engine_hours=100,
    status1=Status1.OVER_TEMPERATURE | Status1.LOW_SYSTEM_VOLTAGE,
    status2=Status2.WARNING_LEVEL_1)


def test_known_vector():
    assert encode(STATE) == VECTOR
    result = decode(VECTOR)
    for field in fields(STATE):
        actual, expected = getattr(result, field.name), getattr(STATE, field.name)
        if expected is None:
            assert actual is None
        elif field.name in ('status1', 'status2'):
            assert actual == expected
        else:
            assert actual == pytest.approx(expected)
    assert active_status(result) == ['OVER_TEMPERATURE', 'LOW_SYSTEM_VOLTAGE', 'WARNING_LEVEL_1']


@pytest.mark.parametrize('field,value,tolerance', [
    ('oil_pressure_pa', 245678, 50), ('oil_temperature_k', 330.17, .05),
    ('coolant_temperature_k', 353.154, .005), ('alternator_voltage_v', 14.204, .005),
    ('fuel_rate_lph', 12.34, .05), ('engine_hours', 100.12345, .5/3600),
    ('coolant_pressure_pa', 123456, 50), ('fuel_pressure_pa', 250123, 500),
    ('engine_load_pct', 37, 0), ('engine_torque_pct', -15, 0),
    ('alternator_voltage_v', -1.25, .005), ('fuel_rate_lph', -1.2, .05),
])
def test_resolutions(field, value, tolerance):
    state = replace(DynamicUpdate(), **{field: value})
    assert abs(getattr(decode(encode(state)), field) - value) <= tolerance + 1e-10


@pytest.mark.parametrize('sentinel_offset', [0, 1, 2])
def test_numeric_sentinels(sentinel_offset):
    data = bytearray(encode(DynamicUpdate(instance=None)))
    for offset in (1, 3, 5, 15, 17):
        struct.pack_into('<H', data, offset, 65535 - sentinel_offset)
    for offset in (7, 9):
        struct.pack_into('<h', data, offset, 32767 - sentinel_offset)
    struct.pack_into('<I', data, 11, 0xffffffff - sentinel_offset)
    for offset in (0, 24, 25):
        data[offset] = (255 if offset == 0 else 127) - sentinel_offset
    result = decode(data)
    assert all(getattr(result, field.name) is None for field in fields(result)
               if field.name not in ('status1', 'status2'))


def test_status_all_bits_are_not_numeric_sentinel():
    state = DynamicUpdate(status1=65535, status2=65535)
    assert decode(encode(state)).status1 == 65535
    assert decode(encode(state)).status2 == 65535
    assert len(active_status(state)) == 24


@pytest.mark.parametrize('field,value', [('oil_pressure_pa', -1), ('instance', 253),
    ('coolant_temperature_k', 655.33), ('alternator_voltage_v', 327.65),
    ('fuel_rate_lph', float('inf')), ('engine_hours', float('nan')),
    ('engine_load_pct', 125), ('engine_torque_pct', -129),
    ('status1', -1), ('status2', 65536), ('status1', None)])
def test_invalid(field, value):
    with pytest.raises(ValueError):
        encode(replace(DynamicUpdate(), **{field: value}))


@pytest.mark.parametrize('length', [0, 25, 27])
def test_invalid_length(length):
    with pytest.raises(ValueError):
        decode(bytes(length))


def test_dynamic_model():
    idle, cruise = sample_dynamic(0), sample_dynamic(15)
    assert idle.coolant_temperature_k == 293.15
    assert cruise.coolant_temperature_k > idle.coolant_temperature_k
    assert cruise.oil_pressure_pa > idle.oil_pressure_pa
    assert cruise.fuel_rate_lph > idle.fuel_rate_lph
    assert cruise.engine_hours == 100 + 13/3600
    assert idle.oil_temperature_k is None and idle.coolant_pressure_pa is None
    assert idle.fuel_pressure_pa is None and idle.engine_load_pct is None
    assert idle.engine_torque_pct is None
    assert idle.status1 == idle.status2 == 0


def message(data, source=35):
    return can.Message(arbitration_id=compose(127489, source), is_extended_id=True, data=data)


def test_decoder_emits_only_complete_packets():
    decoder = Decoder()
    frames = fragment(VECTOR, 0)
    assert all(decoder.receive(message(frame)) is None for frame in frames[:-1])
    assert decoder.receive(message(frames[-1])).engine_hours == 100
    # Duplicate final cannot emit a second telemetry record.
    assert decoder.receive(message(frames[-1])) is None


def test_decoder_damaged_packet_recovery():
    now = [0.0]
    decoder = Decoder(Reassembler(clock=lambda: now[0]))
    frames = fragment(VECTOR, 0)
    for index in (0, 2, 3):
        assert decoder.receive(message(frames[index])) is None
    decoder.receive(message(frames[0]))
    now[0] = 1
    assert all(decoder.receive(message(frame)) is None for frame in frames[1:])
    assert [decoder.receive(message(frame)) for frame in fragment(VECTOR, 1)][-1] is not None


def test_complete_wrong_length_does_not_poison_receiver():
    decoder = Decoder()
    with pytest.raises(ValueError, match='26 bytes'):
        for frame in fragment(bytes(25), 0):
            decoder.receive(message(frame))
    assert [decoder.receive(message(frame)) for frame in fragment(VECTOR, 1)][-1] is not None
