"""Validated 26-byte PGN 127489 layout. Units are explicit in field names.

References and unsupported-field policy are documented in README.md.
Status words are bitfields, not numeric quantities with sentinel values.
"""
import struct
from dataclasses import dataclass, fields
from enum import IntFlag
from .pgn_127488 import _quantize

PGN = 127489


class Status1(IntFlag):
    CHECK_ENGINE = 1 << 0
    OVER_TEMPERATURE = 1 << 1
    LOW_OIL_PRESSURE = 1 << 2
    LOW_OIL_LEVEL = 1 << 3
    LOW_FUEL_PRESSURE = 1 << 4
    LOW_SYSTEM_VOLTAGE = 1 << 5
    LOW_COOLANT_LEVEL = 1 << 6
    WATER_FLOW = 1 << 7
    WATER_IN_FUEL = 1 << 8
    CHARGE_INDICATOR = 1 << 9
    PREHEAT_INDICATOR = 1 << 10
    HIGH_BOOST_PRESSURE = 1 << 11
    REV_LIMIT_EXCEEDED = 1 << 12
    EGR_SYSTEM = 1 << 13
    THROTTLE_POSITION_SENSOR = 1 << 14
    EMERGENCY_STOP = 1 << 15


class Status2(IntFlag):
    WARNING_LEVEL_1 = 1 << 0
    WARNING_LEVEL_2 = 1 << 1
    POWER_REDUCTION = 1 << 2
    MAINTENANCE_NEEDED = 1 << 3
    ENGINE_COMM_ERROR = 1 << 4
    SECONDARY_THROTTLE = 1 << 5
    NEUTRAL_START_PROTECT = 1 << 6
    ENGINE_SHUTTING_DOWN = 1 << 7


@dataclass(frozen=True)
class DynamicUpdate:
    instance: int | None = 0
    oil_pressure_pa: float | None = None
    oil_temperature_k: float | None = None
    coolant_temperature_k: float | None = None
    alternator_voltage_v: float | None = None
    fuel_rate_lph: float | None = None
    engine_hours: float | None = None
    coolant_pressure_pa: float | None = None
    fuel_pressure_pa: float | None = None
    status1: int = 0
    status2: int = 0
    engine_load_pct: int | None = None
    engine_torque_pct: int | None = None


# Field order, little-endian format, resolution in public units. Engine hours
# is seconds on the wire; the public value is hours. Reserved byte is separate.
_LAYOUT = (
    ('B', 1), ('H', 100), ('H', .1), ('H', .01), ('h', .01), ('h', .1),
    ('I', 1 / 3600), ('H', 100), ('H', 1000),
    ('H', None), ('H', None), ('b', 1), ('b', 1),
)


def _limits(fmt: str) -> tuple[int, int, int]:
    bits = struct.calcsize(fmt) * 8
    maximum = (1 << (bits - 1 if fmt.islower() else bits)) - 1
    minimum = -(1 << (bits - 1)) if fmt.islower() else 0
    return minimum, maximum - 3, maximum


def encode(state: DynamicUpdate) -> bytes:
    result = bytearray()
    for index, (field, (fmt, resolution)) in enumerate(zip(fields(state), _LAYOUT)):
        if index == 9:
            result.append(255)
        value = getattr(state, field.name)
        if resolution is None:
            if not isinstance(value, int) or not 0 <= value <= 65535:
                raise ValueError('status must be a 16-bit bitfield')
            raw = value
        else:
            low, high, unavailable = _limits(fmt)
            raw = _quantize(value, resolution, low, high, unavailable)
        result.extend(struct.pack('<' + fmt, raw))
    return bytes(result)


def decode(payload: bytes) -> DynamicUpdate:
    if len(payload) != 26:
        raise ValueError('PGN 127489 requires exactly 26 bytes')
    values = []
    offset = 0
    for index, (fmt, resolution) in enumerate(_LAYOUT):
        if index == 9:
            offset += 1
        raw = struct.unpack_from('<' + fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        if resolution is None:
            values.append(raw)
        else:
            _, high, _ = _limits(fmt)
            values.append(raw * resolution if raw <= high else None)
    return DynamicUpdate(*values)


def active_status(state: DynamicUpdate) -> list[str]:
    return [flag.name for enum, word in ((Status1, state.status1), (Status2, state.status2))
            for flag in enum if word & flag]
