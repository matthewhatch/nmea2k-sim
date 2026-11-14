"""Bounded, ordered NMEA fast-packet transport (not ISO-TP).

Header: 3-bit sequence and 5-bit counter. Frame zero carries length and
six bytes; continuations carry seven. Only complete packets are returned.
"""
from collections import Counter
import math
import time
from dataclasses import dataclass
from typing import Callable

MAX_PAYLOAD = 223


def fragment(payload: bytes, sequence: int) -> list[bytes]:
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('fast-packet payload must contain 1–223 bytes')
    if not 0 <= sequence <= 7:
        raise ValueError('sequence must be 0–7')
    header = sequence << 5
    frames = [(bytes([header, len(payload)]) + payload[:6]).ljust(8, b'\xff')]
    for counter, offset in enumerate(range(6, len(payload), 7), 1):
        frames.append((bytes([header | counter]) + payload[offset:offset + 7]).ljust(8, b'\xff'))
    return frames


@dataclass
class _Pending:
    length: int
    payload: bytearray
    next_counter: int
    started: float


class Reassembler:
    """Single-reader reassembly, isolated by source/PGN/destination/sequence.

    Timeout is an absolute packet lifetime. Duplicates, loss, reordered frames,
    and malformed frames discard that assembly. A new first frame is required
    to recover. Oldest assemblies are evicted when capacity is reached.
    """

    def __init__(self, timeout: float = .75, max_packets: int = 64,
                 clock: Callable[[], float] = time.monotonic):
        if not math.isfinite(timeout) or timeout <= 0 or max_packets < 1:
            raise ValueError('timeout and capacity must be positive')
        self.timeout = timeout
        self.max_packets = max_packets
        self.clock = clock
        self._errors: Counter[str] = Counter()
        self._pending: dict[tuple[int, int, int | None, int], _Pending] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def error_counts(self) -> dict[str, int]:
        return dict(self._errors)

    def expire(self) -> None:
        now = self.clock()
        for key, packet in list(self._pending.items()):
            if now - packet.started >= self.timeout:
                del self._pending[key]
                self._errors['timeout'] += 1

    def feed(self, source: int, pgn: int, data: bytes,
             destination: int | None = None) -> bytes | None:
        self.expire()
        if not data:
            self._errors['invalid_frame_length'] += 1
            return None
        sequence, counter = data[0] >> 5, data[0] & 31
        key = (source, pgn, destination, sequence)
        if len(data) > 8 or len(data) < 2:
            self._pending.pop(key, None)
            self._errors['invalid_frame_length'] += 1
            return None
        if counter == 0:
            if key in self._pending:
                # Ambiguous duplicate/restart: abandon rather than mix payloads.
                del self._pending[key]
                self._errors['duplicate_start'] += 1
                return None
            length = data[1]
            if not 1 <= length <= MAX_PAYLOAD or len(data) < 2 + min(length, 6):
                self._errors['invalid_payload_length'] += 1
                return None
            if length <= 6:
                return bytes(data[2:2 + length])
            if len(self._pending) >= self.max_packets:
                oldest = min(self._pending, key=lambda item: self._pending[item].started)
                del self._pending[oldest]
                self._errors['capacity_eviction'] += 1
            self._pending[key] = _Pending(length, bytearray(data[2:]), 1, self.clock())
            return None
        packet = self._pending.get(key)
        if packet is None:
            self._errors['orphan_frame'] += 1
            return None
        remaining = packet.length - len(packet.payload)
        if counter != packet.next_counter or len(data) < 1 + min(remaining, 7):
            del self._pending[key]
            self._errors['unexpected_counter' if counter != packet.next_counter else 'truncated_frame'] += 1
            return None
        packet.payload.extend(data[1:1 + min(remaining, 7)])
        packet.next_counter += 1
        if len(packet.payload) == packet.length:
            del self._pending[key]
            return bytes(packet.payload)
        return None
