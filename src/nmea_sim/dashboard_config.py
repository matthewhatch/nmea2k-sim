"""Native dashboard settings; shares CAN channel validation with CLI consumers."""
import argparse
import math
import os
from dataclasses import dataclass
from pathlib import Path
from .config import validate_channel


@dataclass(frozen=True)
class DashboardConfig:
    channel: str = 'vcan0'
    stale_after: float = 3.0
    source_address: int | None = None
    engine_instance: int | None = None
    quit_after: float | None = None
    snapshot: Path | None = None
    screenshot: Path | None = None
    transport: str = 'socketcan'
    host: str = ''
    port: int = 29536


def parse_dashboard_config(argv=None) -> DashboardConfig:
    parser = argparse.ArgumentParser(description='Native receive-only NMEA 2000 engine instruments')
    parser.add_argument('--transport', choices=('socketcan', 'socketcand'), default=os.getenv('NMEA_TRANSPORT', 'socketcan'))
    parser.add_argument('--host', default=os.getenv('NMEA_GATEWAY_HOST', ''))
    parser.add_argument('--port', type=int, default=os.getenv('NMEA_GATEWAY_PORT', '29536'))
    parser.add_argument('--channel', default=os.getenv('NMEA_CAN_CHANNEL', 'vcan0'))
    parser.add_argument('--stale-after', type=float, default=3.0, help='per-PGN freshness timeout in seconds')
    parser.add_argument('--source-address', type=int, help='initial engine selection, not a CAN transmit address')
    parser.add_argument('--engine-instance', type=int, help='initial engine selection')
    parser.add_argument('--quit-after', type=float, help='optional bounded demonstration duration')
    parser.add_argument('--snapshot', type=Path, help='write one diagnostic JSON snapshot on exit')
    parser.add_argument('--screenshot', type=Path, help='save a PNG when the bounded demonstration ends')
    args = parser.parse_args(argv)
    try:
        validate_channel(args.channel)
    except ValueError as exc:
        parser.error(str(exc))
    if args.transport not in ('socketcan', 'socketcand'):
        parser.error('invalid transport')
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1–65535')
    if args.transport == 'socketcand' and (not args.host.strip() or len(args.channel) > 16):
        parser.error('socketcand requires --host and a channel of at most 16 characters')
    for name in ('stale_after', 'quit_after'):
        value = getattr(args, name)
        if value is not None and (not math.isfinite(value) or value <= 0):
            parser.error(f'{name} must be finite and positive')
    for name, maximum in (('source_address', 251), ('engine_instance', 252)):
        value = getattr(args, name)
        if value is not None and not 0 <= value <= maximum:
            parser.error(f'{name} must be 0–{maximum}')
    if args.screenshot and args.quit_after is None:
        parser.error('--screenshot requires --quit-after')
    return DashboardConfig(**vars(args))
