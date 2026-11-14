"""Receive-only SocketCAN/decoder integration; no presentation or simulator state."""
import time
from collections import deque
from dataclasses import dataclass
from threading import Event
from PySide6.QtCore import QThread, Signal
import can
from .dashboard_config import DashboardConfig
from .receive_transport import open_receive_transport
from .receiver import Decoder


@dataclass(frozen=True)
class ReceivedFrame:
    message: can.Message
    state: object | None
    error: str = ''
    transport: str = 'socketcan'


class CanReceiver(QThread):
    batchReceived = Signal(object)
    connectionChanged = Signal(str, str)

    def __init__(self, channel: str | DashboardConfig, parent=None):
        super().__init__(parent)
        self.config = channel if isinstance(channel, DashboardConfig) else DashboardConfig(channel=channel)
        self.channel = self.config.channel
        self._stop = Event()
        self._ack = Event()
        self._ack.set()

    def acknowledge(self):
        self._ack.set()

    def stop(self):
        self.requestInterruption()
        self._stop.set()

    def run(self):
        decoder = Decoder()
        pending = []
        dropped = 0
        received = decoded_count = 0
        malformed = 0
        last_emit = started = time.monotonic()
        recent = deque(maxlen=10000)
        attempts = transport_errors = parsing_errors = 0
        last_timestamp = None
        while not self.isInterruptionRequested():
            bus = None
            try:
                self.connectionChanged.emit('connecting' if attempts == 0 else 'reconnecting',
                    f'{self.config.transport} {self.channel} {self.config.host}:{self.config.port} · attempt {attempts}')
                bus = open_receive_transport(self.config)
                decoder = Decoder()  # never combine fragments across connections
                recent.clear()
                self.connectionChanged.emit('connected', f'{self.config.transport} {self.channel} · receive only')
                while not self.isInterruptionRequested():
                    message = bus.recv(.05)
                    if message is not None:
                        received += 1
                        last_timestamp = message.timestamp
                        recent.append(time.monotonic())
                        error = ''
                        try:
                            state = decoder.receive(message)
                        except (ValueError, OverflowError) as exc:
                            state, error = None, str(exc)
                            malformed += 1
                        if state is not None:
                            decoded_count += 1
                        if len(pending) == 256:
                            pending.pop(0)
                            dropped += 1
                        pending.append(ReceivedFrame(message, state, error, self.config.transport))
                    else:
                        decoder.reassembler.expire()
                    now = time.monotonic()
                    while recent and now - recent[0] >= 1:
                        recent.popleft()
                    if now - last_emit >= .05 and self._ack.is_set():
                        self._ack.clear()  # at most one queued batch, plus 256 pending frames
                        self.batchReceived.emit({'frames': pending, 'received': received, 'decoded_count': decoded_count,
                            'malformed': malformed, 'dropped': dropped,
                            'rate': len(recent) / min(1, max(.1, now - started)),
                            'fast_errors': decoder.reassembler.error_counts, 'reconnections': attempts,
                            'transport_errors': transport_errors, 'parsing_errors': parsing_errors,
                            'last_timestamp': last_timestamp})
                        pending = []
                        last_emit = now
            except (ValueError, OSError, can.CanError) as exc:
                transport_errors += 1
                parsing_errors += isinstance(exc, ValueError)
                dropped += len(pending)
                pending = []
                self.connectionChanged.emit('error', str(exc))
                if self.config.transport == 'socketcan':
                    return
                attempts += 1
                self.connectionChanged.emit('reconnecting',
                    f'{self.config.host}:{self.config.port}/{self.channel}: {exc}; retry {attempts}')
                # Same acknowledgement gate bounds diagnostics while offline.
                if self._ack.is_set():
                    self._ack.clear()
                    self.batchReceived.emit({'frames': [], 'received': received, 'decoded_count': decoded_count,
                        'malformed': malformed, 'dropped': dropped, 'rate': 0,
                        'fast_errors': decoder.reassembler.error_counts, 'reconnections': attempts,
                        'transport_errors': transport_errors, 'parsing_errors': parsing_errors,
                        'last_timestamp': last_timestamp})
                self._stop.wait(min(2, .2 * 2 ** min(attempts - 1, 4)))
            finally:
                if bus is not None:
                    bus.close()
        self.connectionChanged.emit('disconnected', 'Receiver stopped')
