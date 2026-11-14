"""Network-management wire codecs; references in docs/protocol-matrix.md.

All multibyte integers are little endian. Product codes/certification metadata
are unavailable by default; no manufacturer assignment or certification is implied.
"""
import struct
from dataclasses import dataclass

ACK = 59392
REQUEST = 59904
CLAIM = 60928
PGN_LIST = 126464
HEARTBEAT = 126993
PRODUCT = 126996
CONFIGURATION = 126998
FAST_PGNS = frozenset((PGN_LIST, PRODUCT, CONFIGURATION, 127489))


def uint(value: int, bits: int) -> int:
    if not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f'expected unsigned {bits}-bit integer')
    return value


@dataclass(frozen=True)
class Name:
    unique_number: int
    manufacturer_code: int
    device_instance: int = 0
    device_function: int = 140  # Propulsion / Engine, not a proprietary identity
    device_class: int = 50
    system_instance: int = 0
    industry_group: int = 4
    arbitrary_address_capable: int = 1

    @property
    def value(self) -> int:
        result = 0
        for value, bits, offset in (
            (self.unique_number, 21, 0), (self.manufacturer_code, 11, 21),
            (self.device_instance, 8, 32), (self.device_function, 8, 40),
            (self.device_class, 7, 49), (self.system_instance, 4, 56),
            (self.industry_group, 3, 60), (self.arbitrary_address_capable, 1, 63),
        ):
            result |= uint(value, bits) << offset
        return result  # bit 48 is spare, zero

    def encode(self) -> bytes:
        return self.value.to_bytes(8, 'little')

    @classmethod
    def decode(cls, data: bytes):
        if len(data) != 8:
            raise ValueError('ISO NAME requires eight bytes')
        value = int.from_bytes(data, 'little')
        return cls(value & 0x1fffff, (value >> 21) & 2047, (value >> 32) & 255,
                   (value >> 40) & 255, (value >> 49) & 127, (value >> 56) & 15,
                   (value >> 60) & 7, value >> 63)


@dataclass(frozen=True)
class ProductInformation:
    nmea_version: int | None = None  # raw AABBB version number
    product_code: int | None = None
    model_id: str = 'NMEA Engine Sim TEST'
    software_version: str = '0.1.0'
    model_version: str = 'virtual-development'
    serial_code: str = ''
    certification_level: int | None = None
    load_equivalency: int | None = None

    def encode(self) -> bytes:
        header = struct.pack('<HH', _optional(self.nmea_version, 16), _optional(self.product_code, 16))
        strings = b''.join(_fixed(s) for s in (self.model_id, self.software_version,
                                              self.model_version, self.serial_code))
        return header + strings + bytes((_optional(self.certification_level, 8),
                                         _optional(self.load_equivalency, 8)))

    @classmethod
    def decode(cls, data: bytes):
        if len(data) not in (132, 134):
            raise ValueError('product information requires 132 or 134 bytes')
        version, product = struct.unpack_from('<HH', data)
        strings = [_read_fixed(data[i:i+32]) for i in (4, 36, 68, 100)]
        cert, load = data[132:134] if len(data) == 134 else (255, 255)
        return cls(_available(version, 16), _available(product, 16), *strings,
                   _available(cert, 8), _available(load, 8))


def _optional(value, bits):
    if value is None:
        return (1 << bits) - 1
    if uint(value, bits) > (1 << bits) - 4:
        raise ValueError('numeric metadata overlaps a sentinel')
    return value


def _available(value, bits):
    return value if value < (1 << bits) - 3 else None


def _fixed(text: str) -> bytes:
    raw = text.encode('ascii')
    if len(raw) > 32 or b'\x00' in raw:
        raise ValueError('product strings must be at most 32 ASCII bytes without NUL')
    return raw.ljust(32, b'\x00')


def _read_fixed(raw: bytes) -> str:
    return raw.split(b'\x00', 1)[0].split(b'\xff', 1)[0].decode('ascii').rstrip()


@dataclass(frozen=True)
class ConfigurationInformation:
    installation_description1: str = 'Virtual engine test device'
    installation_description2: str = 'Not for operational vessels'
    manufacturer_information: str = 'Unassigned development identity'

    def encode(self) -> bytes:
        result = b''.join(_lau(s) for s in (self.installation_description1,
                                           self.installation_description2,
                                           self.manufacturer_information))
        if len(result) > 223:
            raise ValueError('configuration exceeds fast-packet capacity')
        return result

    @classmethod
    def decode(cls, data: bytes):
        values = []
        offset = 0
        for _ in range(3):
            if offset + 2 > len(data):
                raise ValueError('truncated configuration string header')
            length, control = data[offset:offset+2]
            if length < 2 or offset + length > len(data) or control not in (0, 1):
                raise ValueError('invalid configuration string length or encoding')
            raw = data[offset+2:offset+length]
            values.append(raw.decode('utf-16-le' if control == 0 else 'ascii').rstrip('\x00'))
            offset += length
        if offset != len(data):
            raise ValueError('trailing configuration payload bytes')
        return cls(*values)


def _lau(text: str) -> bytes:
    raw = text.encode('ascii')
    if len(raw) > 253 or b'\x00' in raw:
        raise ValueError('configuration string too long or contains NUL')
    return bytes((len(raw) + 2, 1)) + raw


@dataclass(frozen=True)
class PgnList:
    function: int  # 0 = transmit; 1 = receive
    pgns: tuple[int, ...]

    def encode(self) -> bytes:
        if self.function not in (0, 1) or len(self.pgns) > 74:
            raise ValueError('invalid PGN-list function or capacity')
        return bytes((self.function,)) + b''.join(encode_request(pgn) for pgn in self.pgns)

    @classmethod
    def decode(cls, data: bytes):
        if not data or len(data) > 223 or data[0] not in (0, 1) or (len(data) - 1) % 3:
            raise ValueError('invalid PGN-list payload')
        return cls(data[0], tuple(decode_request(data[i:i+3]) for i in range(1, len(data), 3)))


def encode_request(pgn: int) -> bytes:
    if not 0 <= pgn <= 0x3ffff or ((pgn >> 8) & 255 < 240 and pgn & 255):
        raise ValueError('invalid requested PGN')
    return pgn.to_bytes(3, 'little')


def decode_request(data: bytes) -> int:
    if len(data) != 3:
        raise ValueError('ISO request must contain three bytes')
    result = int.from_bytes(data, 'little')
    encode_request(result)
    return result


@dataclass(frozen=True)
class IsoRequest:
    requested_pgn: int

    def encode(self) -> bytes:
        return encode_request(self.requested_pgn)

    @classmethod
    def decode(cls, data: bytes):
        return cls(decode_request(data))


@dataclass(frozen=True)
class Acknowledgement:
    control: int
    group_function: int
    requested_pgn: int

    def encode(self) -> bytes:
        if self.control not in range(4):
            raise ValueError('invalid acknowledgement control')
        return bytes((self.control, uint(self.group_function, 8))) + b'\xff'*3 + encode_request(self.requested_pgn)

    @classmethod
    def decode(cls, data: bytes):
        if len(data) != 8 or data[0] > 3:
            raise ValueError('invalid ISO acknowledgement')
        return cls(data[0], data[1], decode_request(data[5:8]))


@dataclass(frozen=True)
class Heartbeat:
    interval_ms: int = 6000
    sequence: int = 0
    controller1: int = 3  # hardware controller states are unavailable
    controller2: int = 3
    equipment_status: int = 0

    def encode(self) -> bytes:
        if not 1000 <= self.interval_ms <= 60000 or not 0 <= self.sequence <= 252:
            raise ValueError('invalid heartbeat interval/counter')
        states = uint(self.controller1, 2) | uint(self.controller2, 2) << 2 | uint(self.equipment_status, 2) << 4
        return struct.pack('<HB', self.interval_ms, self.sequence) + bytes((states | 0xc0,)) + b'\xff'*4

    @classmethod
    def decode(cls, data: bytes):
        if len(data) != 8:
            raise ValueError('heartbeat requires eight bytes')
        interval, sequence = struct.unpack_from('<HB', data)
        return cls(interval, sequence, data[3] & 3, (data[3] >> 2) & 3, (data[3] >> 4) & 3)


DECODERS = {REQUEST: IsoRequest.decode, CLAIM: Name.decode, PRODUCT: ProductInformation.decode,
            CONFIGURATION: ConfigurationInformation.decode, PGN_LIST: PgnList.decode,
            HEARTBEAT: Heartbeat.decode, ACK: Acknowledgement.decode}
