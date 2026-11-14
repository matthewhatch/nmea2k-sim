from dataclasses import replace
import struct
import can
import pytest
from nmea_sim import device_protocol as p
from nmea_sim.can_id import compose, extract
from nmea_sim.device import Device, ClaimState, TX_PGNS, RX_PGNS
from nmea_sim.fast_packet import Reassembler
from nmea_sim.consumer import Decoder


def incoming(pgn, data, source=80, destination=255, **kwargs):
    return can.Message(arbitration_id=compose(pgn, source, 6, destination),
                       data=data, is_extended_id=True, **kwargs)


def claimed(unique=100, address=35):
    device = Device(p.Name(unique, 2046), address)
    device.start(0)
    device.tick(.25)
    return device


def test_name_known_vector_and_bit_boundaries():
    assert p.Name(1, 2046).encode() == bytes.fromhex('01 00 c0 ff 00 8c 64 c0')
    assert p.Name.decode(bytes.fromhex('01 00 c0 ff 00 8c 64 c0')) == p.Name(1, 2046)
    name = p.Name(0x1fffff, 2047, 255, 255, 127, 15, 7, 1)
    assert name.value == 0xfffeffffffffffff  # spare bit 48 stays clear
    assert p.Name.decode(name.encode()) == name
    assert p.Name(1, 2046, 0xA5).encode()[4] == 0xA5  # lower 3 / upper 5 bits


@pytest.mark.parametrize('field,value', [('unique_number', -1), ('unique_number', 0x200000),
    ('manufacturer_code', 2048), ('device_instance', 256), ('device_class', 128),
    ('device_function', 256), ('system_instance', 16), ('industry_group', 8)])
def test_name_invalid(field, value):
    with pytest.raises(ValueError):
        replace(p.Name(1, 2046), **{field:value}).encode()


def test_product_wire_vector_and_unavailable_metadata():
    product = p.ProductInformation(model_id='TEST', serial_code='0001')
    raw = product.encode()
    assert len(raw) == 134
    assert raw[:4] == b'\xff'*4
    assert raw[4:36] == b'TEST' + bytes(28)
    assert raw[100:132] == b'0001' + bytes(28)
    assert raw[132:] == b'\xff\xff'  # no false Level A certification
    assert p.ProductInformation.decode(raw) == product
    assert p.ProductInformation.decode(raw[:132]).certification_level is None


def test_configuration_string_vector():
    config = p.ConfigurationInformation('A', '', 'B')
    raw = bytes.fromhex('03 01 41 02 01 03 01 42')
    assert config.encode() == raw
    assert p.ConfigurationInformation.decode(raw) == config
    assert p.ConfigurationInformation.decode(bytes.fromhex('04 00 41 00 02 01 02 01')).installation_description1 == 'A'


@pytest.mark.parametrize('data', [b'', b'\x01\x01', b'\x03\x01', b'\x02\x02',
    bytes.fromhex('02 01 02 01 02 01 ff')])
def test_malformed_configuration(data):
    with pytest.raises(ValueError):
        p.ConfigurationInformation.decode(data)


def test_string_limits():
    with pytest.raises(ValueError):
        p.ProductInformation(model_id='X'*33).encode()
    with pytest.raises(ValueError):
        p.ConfigurationInformation('X'*100, 'Y'*100, 'Z'*100).encode()
    with pytest.raises(ValueError):
        p.ConfigurationInformation('bad\x00string').encode()


def test_pgn_list_vector():
    raw = bytes.fromhex('00 00 f2 01 01 f2 01')
    assert p.PgnList(0, (127488, 127489)).encode() == raw
    assert p.PgnList.decode(raw) == p.PgnList(0, (127488, 127489))


@pytest.mark.parametrize('data', [b'', b'\x02', b'\x00\xff', b'\x00\xff\xff\xff'])
def test_bad_pgn_list(data):
    with pytest.raises(ValueError):
        p.PgnList.decode(data)


def test_request_ack_heartbeat_vectors():
    assert p.encode_request(p.PRODUCT) == bytes.fromhex('14 f0 01')
    ack = p.Acknowledgement(1, 255, 127508)
    assert ack.encode() == bytes.fromhex('01 ff ff ff ff 14 f2 01')
    assert p.Acknowledgement.decode(ack.encode()) == ack
    heartbeat = p.Heartbeat(sequence=252)
    assert heartbeat.encode() == bytes.fromhex('70 17 fc cf ff ff ff ff')
    assert p.Heartbeat.decode(heartbeat.encode()) == heartbeat


def test_claim_wait_gates_all_application_frames():
    device = Device(p.Name(100, 2046))
    claim = device.start(10)[0]
    assert (claim.pgn, claim.priority, claim.source, claim.destination) == (60928, 6, 35, 255)
    assert device.tick(10.249) == []
    assert not device.owns_address
    assert device.engine_message(127488, bytes(8)) == []
    assert device.receive(incoming(p.REQUEST, p.encode_request(p.PRODUCT), destination=35), 10.1) == []
    assert device.tick(10.25)[0].pgn == p.HEARTBEAT
    assert device.owns_address
    assert device.engine_message(127488, bytes(8))[0].source == 35


def test_losing_conflict_reclaims_and_pauses():
    device = claimed()
    result = device.receive(incoming(p.CLAIM, p.Name(1, 2046).encode(), source=35), 1)
    assert result[0].pgn == p.CLAIM and result[0].source == 36
    assert not device.owns_address
    assert device.engine_message(127488, bytes(8)) == []
    device.tick(1.25)
    assert device.engine_message(127488, bytes(8))[0].source == 36


def test_winning_conflict_reasserts_and_waits():
    device = claimed()
    result = device.receive(incoming(p.CLAIM, p.Name(101, 2046).encode(), source=35), 1)
    assert result[0].source == 35
    assert not device.owns_address
    device.tick(1.25)
    assert device.owns_address


def test_free_selection_skips_observed_nodes_and_wraps():
    device = claimed(address=251)
    device.receive(incoming(p.CLAIM, p.Name(3, 2046).encode(), source=0), .5)
    result = device.receive(incoming(p.CLAIM, p.Name(1, 2046).encode(), source=251), 1)
    assert result[0].source == 1


def test_unclaimed_traffic_also_causes_yield():
    device = claimed()
    assert device.receive(incoming(127488, bytes(8), source=35), 1)[0].source == 36
    assert not device.owns_address


def test_no_addresses_cannot_claim_and_no_engine_tx():
    device = claimed()
    for address in range(252):
        if address != 35:
            device.receive(incoming(p.CLAIM, p.Name(1000 + address, 2046).encode(), source=address), .5)
    result = device.receive(incoming(p.CLAIM, p.Name(1, 2046).encode(), source=35), 1)
    assert result[0].source == 254 and device.state == ClaimState.CANNOT_CLAIM
    assert device.engine_message(127488, bytes(8)) == []
    request = incoming(p.REQUEST, p.encode_request(p.CLAIM))
    assert device.receive(request, 2)[0].source == 254


@pytest.mark.parametrize('source', [35, 36])
def test_duplicate_name_fails_closed(source):
    device = claimed()
    with pytest.raises(ValueError, match='duplicate ISO NAME'):
        device.receive(incoming(p.CLAIM, device.name.encode(), source=source), 1)
    assert device.engine_message(127488, bytes(8)) == []


def test_moved_peer_releases_its_old_address():
    device = claimed()
    peer = p.Name(3, 2046).encode()
    device.receive(incoming(p.CLAIM, peer, source=36), 1)
    device.receive(incoming(p.CLAIM, peer, source=37), 2)
    assert 36 not in device.occupied and 37 in device.occupied


@pytest.mark.parametrize('destination', [35, 255])
@pytest.mark.parametrize('requested', [p.CLAIM, p.PRODUCT, p.CONFIGURATION, p.PGN_LIST])
def test_request_reply_reassembles_and_decodes(requested, destination):
    device = claimed()
    replies = device.receive(incoming(p.REQUEST, p.encode_request(requested), destination=destination), 1)
    decoder = Decoder()
    states = []
    for reply in replies:
        assert reply.destination == 255 and reply.priority == 6
        msg = incoming(reply.pgn, reply.data, source=reply.source, destination=reply.destination)
        result = decoder.receive(msg)
        if result is not None:
            states.append(result)
    if requested == p.PGN_LIST:
        assert states == [p.PgnList(0, TX_PGNS), p.PgnList(1, RX_PGNS)]
    else:
        assert len(states) == 1
        assert states[0] == {p.CLAIM: device.name, p.PRODUCT: device.product,
                             p.CONFIGURATION: device.configuration}[requested]


def test_directed_unsupported_nack_and_global_silence():
    device = claimed()
    for requested in (127508, p.HEARTBEAT):
        assert device.receive(incoming(p.REQUEST, p.encode_request(requested)), 1) == []
        reply = device.receive(incoming(p.REQUEST, p.encode_request(requested), destination=35), 1)[0]
        assert reply.pgn == p.ACK and reply.destination == 80
        assert p.Acknowledgement.decode(reply.data).requested_pgn == requested
        assert extract(compose(reply.pgn, reply.source, reply.priority, reply.destination)).pgn == p.ACK


def test_other_destination_malformed_or_null_requests_ignored():
    device = claimed()
    for message in (incoming(p.REQUEST, b'', destination=35),
                    incoming(p.REQUEST, b'\xff\xff\xff', destination=35),
                    incoming(p.REQUEST, p.encode_request(p.PRODUCT), destination=36),
                    incoming(p.REQUEST, p.encode_request(p.PRODUCT), source=254),
                    incoming(p.CLAIM, b'\x00', source=35)):
        assert device.receive(message, 1) == []
    assert device.address == 35


def test_heartbeat_timer_rollover_and_no_iso_trigger():
    device = claimed()
    device.heartbeat_sequence = 252
    heartbeat = device.tick(6.25)[0]
    assert heartbeat.priority == 7
    assert p.Heartbeat.decode(heartbeat.data).sequence == 252
    assert device.tick(6.26) == []
    assert p.Heartbeat.decode(device.tick(12.25)[0].data).sequence == 0


def test_independent_fast_sequence_per_pgn():
    device = claimed()
    for i in range(10):
        reply = device.receive(incoming(p.REQUEST, p.encode_request(p.PRODUCT)), 1)
        assert reply[0].data[0] >> 5 == i % 8
    config = device.receive(incoming(p.REQUEST, p.encode_request(p.CONFIGURATION)), 1)
    assert config[0].data[0] >> 5 == 0
