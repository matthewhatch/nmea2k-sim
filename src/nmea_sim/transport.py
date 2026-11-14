"""SocketCAN lifecycle and actionable startup errors."""
import json
import socket
import subprocess
import can
from .config import Config


def open_bus(config: Config, *, transmit: bool = False):
    try:
        socket.if_nametoindex(config.channel)
    except OSError as exc:
        raise ValueError(f'CAN interface {config.channel!r} does not exist; run sudo scripts/setup_vcan.sh for vcan0') from exc
    if transmit and (config.manufacturer_code == 2046 or not config.allow_physical_tx):
        virtual = is_virtual_can(config.channel)
        if not virtual and config.manufacturer_code == 2046:
            raise ValueError('Unassigned test identity 2046 is restricted to kernel vcan interfaces, even with --allow-physical-tx')
        if not virtual:
            raise ValueError('physical TX requires explicit --allow-physical-tx; use vcan0 for development')
    try:
        return can.Bus(interface='socketcan', channel=config.channel)
    except (OSError, can.CanError) as exc:
        raise ValueError(f'Cannot open {config.channel}: {exc}. Check interface is UP and SocketCAN permissions.') from exc


def is_virtual_can(channel: str) -> bool:
    """Verify kernel interface kind; names alone cannot establish isolation."""
    try:
        result = subprocess.run(['ip', '-json', '-details', 'link', 'show', 'dev', channel],
                                check=True, capture_output=True, text=True, timeout=3)
        links = json.loads(result.stdout)
        return (isinstance(links, list) and len(links) == 1
                and isinstance(links[0], dict)
                and links[0].get('linkinfo', {}).get('info_kind') == 'vcan')
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Cannot verify virtual CAN interface type; install iproute2 and check permissions. '
                         'Transmission refused without --allow-physical-tx.') from exc
