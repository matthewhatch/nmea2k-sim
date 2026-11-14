"""Clock-injected NMEA device protocol, independent of SocketCAN and engine model."""
from dataclasses import dataclass
from enum import StrEnum
import can
from .can_id import extract
from .fast_packet import fragment
from . import device_protocol as p

CLAIM_WAIT = .250
HEARTBEAT_SECONDS = 6.0
TX_PGNS = (p.ACK, p.CLAIM, p.PGN_LIST, p.HEARTBEAT, p.PRODUCT, p.CONFIGURATION, 127488, 127489)
RX_PGNS = (p.REQUEST, p.CLAIM)


class ClaimState(StrEnum):
    NEW = 'new'
    CLAIMING = 'claiming'
    CLAIMED = 'claimed'
    CANNOT_CLAIM = 'cannot_claim'


@dataclass(frozen=True)
class Transmission:
    pgn: int
    data: bytes
    source: int
    destination: int = 255
    priority: int = 6


class Device:
    def __init__(self, name: p.Name, preferred_address: int = 35):
        if not 0 <= preferred_address <= 251:
            raise ValueError('preferred address must be 0–251')
        name.encode()  # validate before emitting anything
        if name.arbitrary_address_capable != 1:
            raise ValueError('this device requires arbitrary address capability')
        self.name = name
        self.address = preferred_address
        self.state = ClaimState.NEW
        self.claim_deadline = 0.0
        self.heartbeat_deadline = float('inf')
        self.heartbeat_sequence = 0
        self.occupied: dict[int, int | None] = {}
        self._sequences: dict[int, int] = {}
        serial = f'NMEA-SIM-{name.unique_number:06X}-{name.device_instance:02X}'
        self.product = p.ProductInformation(serial_code=serial)
        manufacturer = ('Unassigned 2046 vcan test ONLY' if name.manufacturer_code == 2046
                        else 'Operator supplied manufacturer')
        self.configuration = p.ConfigurationInformation(manufacturer_information=manufacturer)

    @property
    def owns_address(self) -> bool:
        return self.state == ClaimState.CLAIMED

    def _claim(self, now: float) -> list[Transmission]:
        self.state = ClaimState.CLAIMING
        self.claim_deadline = now + CLAIM_WAIT
        self.heartbeat_deadline = float('inf')
        return [Transmission(p.CLAIM, self.name.encode(), self.address)]

    def start(self, now: float) -> list[Transmission]:
        if self.state != ClaimState.NEW:
            raise ValueError('device already started')
        return self._claim(now)

    def _relocate(self, now: float) -> list[Transmission]:
        for step in range(1, 253):
            candidate = (self.address + step) % 252
            if candidate not in self.occupied:
                self.address = candidate
                return self._claim(now)
        self.state = ClaimState.CANNOT_CLAIM
        self.heartbeat_deadline = float('inf')
        return [Transmission(p.CLAIM, self.name.encode(), 254)]

    def tick(self, now: float) -> list[Transmission]:
        if self.state == ClaimState.CLAIMING and now >= self.claim_deadline:
            self.state = ClaimState.CLAIMED
            self.heartbeat_deadline = now
        if self.owns_address and now >= self.heartbeat_deadline:
            result = self._message(p.HEARTBEAT, p.Heartbeat(sequence=self.heartbeat_sequence).encode(), priority=7)
            self.heartbeat_sequence = (self.heartbeat_sequence + 1) % 253
            self.heartbeat_deadline = now + HEARTBEAT_SECONDS
            return result
        return []

    def _message(self, pgn: int, payload: bytes, *, priority: int = 6,
                 destination: int = 255) -> list[Transmission]:
        if not self.owns_address:
            return []
        if pgn in p.FAST_PGNS:
            sequence = self._sequences.get(pgn, 0)
            frames = fragment(payload, sequence)
            self._sequences[pgn] = (sequence + 1) % 8
        else:
            if len(payload) > 8:
                raise ValueError('single frame exceeds eight bytes')
            frames = [payload]
        return [Transmission(pgn, data, self.address, destination, priority) for data in frames]

    def engine_message(self, pgn: int, payload: bytes) -> list[Transmission]:
        if pgn not in (127488, 127489):
            raise ValueError('not an engine PGN')
        return self._message(pgn, payload, priority=2)

    def receive(self, message: can.Message, now: float) -> list[Transmission]:
        if (not message.is_extended_id or message.is_remote_frame or message.is_error_frame
                or message.is_fd or len(message.data) > 8):
            return []
        try:
            identifier = extract(message.arbitration_id)
        except ValueError:
            return []
        source, pgn = identifier.source, identifier.pgn
        payload = bytes(message.data)
        if pgn == p.CLAIM:
            if len(payload) != 8 or identifier.destination != 255 or source in (252, 253, 255):
                return []
            peer = int.from_bytes(payload, 'little')
            if peer == self.name.value:
                # SocketCAN suppresses our own socket's echo; equal NAME implies
                # another process/device with a duplicate identity. Fail closed.
                self.state = ClaimState.CANNOT_CLAIM
                self.heartbeat_deadline = float('inf')
                raise ValueError('duplicate ISO NAME detected; select a distinct --unique-number')
            for address, known in list(self.occupied.items()):
                if known == peer:
                    del self.occupied[address]  # peer moved or cannot claim
            if source <= 251:
                self.occupied[source] = peer
            if source == self.address and self.state in (ClaimState.CLAIMING, ClaimState.CLAIMED):
                return self._claim(now) if self.name.value < peer else self._relocate(now)
            return []
        if source <= 251:
            self.occupied.setdefault(source, None)
            if source == self.address and self.state in (ClaimState.CLAIMING, ClaimState.CLAIMED):
                # Traffic at our address without a NAME is also a conflict; do
                # not transmit telemetry over a legacy/unclaimed talker.
                return self._relocate(now)
        if pgn != p.REQUEST or identifier.destination not in (self.address, 255) or source in (252, 253, 255):
            return []
        try:
            requested = p.decode_request(payload)
        except ValueError:
            return []
        if requested == p.CLAIM:
            if self.state == ClaimState.CANNOT_CLAIM:
                return [Transmission(p.CLAIM, self.name.encode(), 254)]
            if self.state in (ClaimState.CLAIMING, ClaimState.CLAIMED):
                return [Transmission(p.CLAIM, self.name.encode(), self.address)]
        if not self.owns_address or source > 251:
            return []
        if requested == p.PRODUCT:
            return self._message(p.PRODUCT, self.product.encode())
        if requested == p.CONFIGURATION:
            return self._message(p.CONFIGURATION, self.configuration.encode())
        if requested == p.PGN_LIST:
            return (self._message(p.PGN_LIST, p.PgnList(0, TX_PGNS).encode())
                    + self._message(p.PGN_LIST, p.PgnList(1, RX_PGNS).encode()))
        # Unsupported directed requests get NACK. No response to unsupported
        # global requests, including heartbeat (not ISO-requestable).
        if identifier.destination == self.address:
            return self._message(p.ACK, p.Acknowledgement(1, 255, requested).encode(), destination=source)
        return []
