"""CANboat PGN 127488 layout; see README for reference and sentinels."""
import math
import struct
from dataclasses import dataclass

PGN = 127488


@dataclass(frozen=True)
class RapidUpdate:
    instance: int | None
    rpm: float | None
    boost_pa: float | None
    trim: int | None


def _quantize(value, resolution, low, high, unavailable):
    if value is None:
        return unavailable
    if not math.isfinite(value) or not low <= value / resolution <= high:
        raise ValueError('field outside supported numeric range')
    return round(value / resolution)


def encode(state: RapidUpdate) -> bytes:
    return struct.pack('<BHHb',
                       _quantize(state.instance, 1, 0, 252, 255),
                       _quantize(state.rpm, .25, 0, 65532, 65535),
                       _quantize(state.boost_pa, 100, 0, 65532, 65535),
                       _quantize(state.trim, 1, -128, 124, 127)) + b'\xff\xff'


def decode(payload: bytes) -> RapidUpdate:
    if len(payload) != 8:
        raise ValueError('PGN 127488 requires exactly eight bytes')
    instance, rpm, boost, trim = struct.unpack('<BHHb', payload[:6])
    return RapidUpdate(instance if instance <= 252 else None,
                       rpm * .25 if rpm <= 65532 else None,
                       boost * 100 if boost <= 65532 else None,
                       trim if trim <= 124 else None)
