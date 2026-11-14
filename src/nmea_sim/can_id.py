"""29-bit J1939/NMEA identifiers, including both data-page bits."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Identifier:
    pgn: int
    source: int
    priority: int
    destination: int | None


def compose(pgn: int, source: int = 35, priority: int = 2, destination: int = 255) -> int:
    if not (0 <= pgn <= 0x3FFFF and 0 <= source <= 255 and 0 <= priority <= 7
            and 0 <= destination <= 255):
        raise ValueError('CAN identifier field out of range')
    pdu1 = (pgn >> 8) & 255 < 240
    if pdu1 and pgn & 255:
        raise ValueError('PDU1 PGN low byte must be zero; use destination')
    return (priority << 26) | (pgn << 8) | source | (destination << 8 if pdu1 else 0)


def extract(identifier: int) -> Identifier:
    if not 0 <= identifier <= 0x1FFFFFFF:
        raise ValueError('expected a 29-bit identifier')
    pgn = (identifier >> 8) & 0x3FFFF
    pdu1 = ((pgn >> 8) & 255) < 240
    return Identifier(pgn & ~255 if pdu1 else pgn, identifier & 255,
                      identifier >> 26, (identifier >> 8) & 255 if pdu1 else None)
