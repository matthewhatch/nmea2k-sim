"""Shared CLI and environment configuration."""
import argparse
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    channel: str
    source_address: int
    allow_physical_tx: bool = False
    count: int | None = None
    timeout: float = 5.0
    rapid_hz: float = 5.0
    dynamic_hz: float = 1.0
    manufacturer_code: int = 2046
    unique_number: int | None = None
    device_instance: int = 0
    system_instance: int = 0
    engine_instance: int = 0
    device_key: str = 'engine-0'


def parse_config(argv=None) -> Config:
    parser = argparse.ArgumentParser()
    parser.add_argument('--channel', default=os.getenv('NMEA_CAN_CHANNEL', 'vcan0'))
    parser.add_argument('--source-address', type=int, default=os.getenv('NMEA_SOURCE_ADDRESS', '35'))
    parser.add_argument('--rapid-hz', type=float, default=os.getenv('NMEA_RAPID_HZ', '5'))
    parser.add_argument('--dynamic-hz', type=float, default=os.getenv('NMEA_DYNAMIC_HZ', '1'))
    parser.add_argument('--manufacturer-code', type=int, default=os.getenv('NMEA_MANUFACTURER_CODE', '2046'))
    parser.add_argument('--unique-number', type=int, default=os.getenv('NMEA_UNIQUE_NUMBER'))
    parser.add_argument('--device-instance', type=int, default=os.getenv('NMEA_DEVICE_INSTANCE', '0'))
    parser.add_argument('--system-instance', type=int, default=os.getenv('NMEA_SYSTEM_INSTANCE', '0'))
    parser.add_argument('--engine-instance', type=int, default=os.getenv('NMEA_ENGINE_INSTANCE', '0'))
    parser.add_argument('--device-key', default=os.getenv('NMEA_DEVICE_KEY', 'engine-0'))
    parser.add_argument('--allow-physical-tx', action='store_true')
    parser.add_argument('--count', type=int, help='exit after this many rapid TX frames or decoded RX messages')
    parser.add_argument('--timeout', type=float, default=5.0, help='receiver inactivity timeout in seconds')
    args = parser.parse_args(argv)
    try:
        validate_channel(args.channel)
    except ValueError as exc:
        parser.error(str(exc))
    if not 0 <= args.source_address <= 251:
        parser.error('source address must be 0–251 (252–255 are reserved or special)')
    if args.count is not None and args.count <= 0:
        parser.error('count must be positive')
    if not 0 < args.timeout < float('inf'):
        parser.error('timeout must be finite and positive')
    for name in ('rapid_hz', 'dynamic_hz'):
        if not 0 < getattr(args, name) <= 100:
            parser.error(f'{name} must be finite and in (0, 100] Hz')
    for name, maximum in (('device_instance', 255), ('system_instance', 15), ('engine_instance', 252)):
        if not 0 <= getattr(args, name) <= maximum:
            parser.error(f'{name} must be 0–{maximum}')
    if not (1 <= args.manufacturer_code <= 2044 or args.manufacturer_code == 2046):
        parser.error('manufacturer code must be 1–2044, or 2046 for virtual tests only')
    if args.unique_number is not None and not 1 <= args.unique_number <= 0x1fffff:
        parser.error('unique number must be 1–2097151')
    if not args.device_key or len(args.device_key) > 128:
        parser.error('device key must contain 1–128 characters')
    return Config(**vars(args))


def stable_unique_number(config: Config) -> int:
    """Stable host/logical-device hash; explicit IDs avoid cross-host collisions."""
    if config.unique_number is not None:
        return config.unique_number
    import hashlib
    from pathlib import Path
    try:
        machine_id = Path('/etc/machine-id').read_text().strip()
    except OSError as exc:
        raise ValueError('Cannot read stable machine ID; set --unique-number') from exc
    if not machine_id:
        raise ValueError('Empty machine ID; set --unique-number')
    digest = hashlib.sha256((machine_id + ':' + config.device_key).encode()).digest()
    return (int.from_bytes(digest[:4], 'little') & 0x1fffff) or 1


def validate_channel(channel: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', channel):
        raise ValueError('channel must be a Linux interface name (1–15 letters, digits, _, . or -)')
    return channel
