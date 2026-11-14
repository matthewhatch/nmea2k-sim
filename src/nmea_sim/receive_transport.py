"""UI-independent, receive-only adapters for native CAN messages.

Socketcand framing follows linux-can/socketcand/doc/protocol.md, RAW mode.
"""
import math
import re
import select
import socket
import time
from typing import Protocol
import can
from .config import Config
from .transport import open_bus


class ReceiveTransport(Protocol):
    def recv(self, timeout: float) -> can.Message | None: ...
    def close(self) -> None: ...


def parse_frame(record: bytes, channel: str) -> can.Message:
    match = re.fullmatch(rb'< frame ([0-9a-fA-F]{3}|[0-9a-fA-F]{8}) (\d+\.\d+) ([0-9a-fA-F]*) >', record)
    if not match:
        raise ValueError('Invalid socketcand RAW frame')
    identifier, timestamp, payload = match.groups()
    if len(payload) > 16 or len(payload) % 2:
        raise ValueError('Invalid classical CAN payload length')
    stamp = float(timestamp)
    if not math.isfinite(stamp):
        raise ValueError('Invalid gateway timestamp')
    return can.Message(arbitration_id=int(identifier, 16), is_extended_id=len(identifier) == 8,
                       data=bytes.fromhex(payload.decode('ascii')), timestamp=stamp,
                       channel=channel, is_rx=True, check=True)


class LocalTransport:
    def __init__(self, config):
        self.bus = open_bus(Config(config.channel, 35), transmit=False)

    def recv(self, timeout):
        return self.bus.recv(timeout)

    def close(self):
        self.bus.shutdown()


class SocketcandTransport:
    """Bounded incremental parser; exposes no CAN send or bus configuration API.

    At most 4096 input bytes plus one record are held. Invalid input is fatal:
    reconnecting also discards incomplete NMEA fast packets in the receiver.
    """
    def __init__(self, config):
        self.channel = config.channel
        self.buffer = bytearray()
        self.socket = socket.create_connection((config.host, config.port), timeout=1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Detect silent network failure without treating a quiet CAN bus as dead.
        for option, value in (('TCP_KEEPIDLE', 10), ('TCP_KEEPINTVL', 3), ('TCP_KEEPCNT', 3)):
            if hasattr(socket, option):
                self.socket.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
        try:
            self._expect(b'< hi >')
            self.socket.sendall(f'< open {config.channel} >'.encode('ascii'))
            self._expect(b'< ok >')
            self.socket.sendall(b'< rawmode >')
            self._expect(b'< ok >')
        except BaseException:
            self.close()
            raise

    def _record(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            end = self.buffer.find(b'>')
            if end >= 0:
                if end >= 128:
                    raise ValueError('Oversized socketcand record')
                record = bytes(self.buffer[:end + 1])
                del self.buffer[:end + 1]
                return record
            if len(self.buffer) > 128:
                raise ValueError('Oversized or truncated socketcand record')
            remaining = max(0, deadline - time.monotonic())
            if not select.select([self.socket], [], [], remaining)[0]:
                return None
            data = self.socket.recv(4096 - len(self.buffer))
            if not data:
                raise ConnectionError('socketcand closed connection' + (' with truncated record' if self.buffer else ''))
            self.buffer.extend(data)

    def _expect(self, expected):
        record = self._record(1)
        if record != expected:
            raise ValueError(f'socketcand handshake expected {expected!r}, received {record!r}')

    def recv(self, timeout):
        record = self._record(timeout)
        return None if record is None else parse_frame(record, self.channel)

    def close(self):
        self.socket.close()


def open_receive_transport(config) -> ReceiveTransport:
    return SocketcandTransport(config) if config.transport == 'socketcand' else LocalTransport(config)
