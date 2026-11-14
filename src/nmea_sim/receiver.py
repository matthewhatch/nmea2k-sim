"""Independent SocketCAN receiver. JSON lines contain only decoded CAN data."""
import json
import logging
from dataclasses import asdict
import can
from .config import parse_config
from .transport import open_bus
from .can_id import extract
from .pgn_127488 import PGN, decode
from . import pgn_127489
from .fast_packet import Reassembler
from . import device_protocol as protocol


def receive_frame(message):
    if (not message.is_extended_id or message.is_error_frame or message.is_remote_frame
            or message.is_fd or extract(message.arbitration_id).pgn != PGN):
        return None
    return decode(bytes(message.data))


class Decoder:
    """One instance per receiving socket; no simulator dependencies."""

    def __init__(self, reassembler=None):
        self.reassembler = reassembler if reassembler is not None else Reassembler()

    def receive(self, message):
        self.reassembler.expire()
        if (not message.is_extended_id or message.is_error_frame or message.is_remote_frame
                or message.is_fd):
            return None
        identifier = extract(message.arbitration_id)
        if identifier.pgn == PGN:
            return decode(bytes(message.data))
        if identifier.pgn in protocol.FAST_PGNS:
            payload = self.reassembler.feed(identifier.source, identifier.pgn,
                                            bytes(message.data), identifier.destination)
            if payload is not None:
                if identifier.pgn == pgn_127489.PGN:
                    return pgn_127489.decode(payload)
                return protocol.DECODERS[identifier.pgn](payload)
            return None
        if identifier.pgn in protocol.DECODERS:
            return protocol.DECODERS[identifier.pgn](bytes(message.data))
        return None


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = parse_config(argv)
    try:
        with open_bus(config) as bus:
            # PDU1 masks omit the destination byte; PDU2 masks retain it.
            bus.set_filters([{'can_id': pgn << 8, 'can_mask': 0x3FF0000 if (pgn >> 8) & 255 < 240 else 0x3FFFF00, 'extended': True}
                             for pgn in (PGN, pgn_127489.PGN, *protocol.DECODERS)])
            decoder = Decoder()
            print(json.dumps({'status': 'ready', 'channel': config.channel}), flush=True)
            count = 0
            while config.count is None or count < config.count:
                message = bus.recv(config.timeout)
                decoder.reassembler.expire()
                if message is None:
                    if config.count is not None:
                        logging.error('No matching CAN telemetry within timeout')
                        return 1
                    continue
                try:
                    state = decoder.receive(message)
                except ValueError as exc:
                    logging.warning('Ignoring malformed frame: %s', exc)
                    continue
                if state is not None:
                    record = {'pgn': extract(message.arbitration_id).pgn,
                              'source': extract(message.arbitration_id).source,
                              'timestamp': message.timestamp, **asdict(state)}
                    if isinstance(state, protocol.Name):
                        record['name'] = f'{state.value:016x}'
                    if isinstance(state, pgn_127489.DynamicUpdate):
                        record['active_status'] = pgn_127489.active_status(state)
                    print(json.dumps(record), flush=True)
                    count += 1
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, can.CanError) as exc:
        logging.error('%s', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
