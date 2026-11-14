"""Receive-only SocketCAN/decoder integration; no presentation or simulator state."""
import time
from collections import deque
from dataclasses import dataclass
from threading import Event
from PySide6.QtCore import QThread, Signal
import can
from .config import Config
from .transport import open_bus
from .receiver import Decoder


@dataclass(frozen=True)
class ReceivedFrame:
    message: can.Message
    state: object | None
    error: str = ''


class CanReceiver(QThread):
    batchReceived = Signal(object)
    connectionChanged = Signal(str, str)

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._ack = Event()
        self._ack.set()

    def acknowledge(self):
        self._ack.set()

    def stop(self):
        self.requestInterruption()

    def run(self):
        decoder = Decoder()
        pending = []
        dropped = 0
        received = decoded_count = 0
        malformed = 0
        last_emit = started = time.monotonic()
        recent = deque(maxlen=10000)
        try:
            with open_bus(Config(self.channel, 35), transmit=False) as bus:
                self.connectionChanged.emit('connected', f'Listening on {self.channel} · receive only')
                while not self.isInterruptionRequested():
                    message = bus.recv(.05)
                    if message is not None:
                        received += 1
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
                        pending.append(ReceivedFrame(message, state, error))
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
                            'fast_errors': decoder.reassembler.error_counts})
                        pending = []
                        last_emit = now
        except (ValueError, OSError, can.CanError) as exc:
            self.connectionChanged.emit('error', str(exc))
