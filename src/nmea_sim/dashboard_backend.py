"""Main-thread Qt bridge: telemetry state, diagnostics and user selection."""
import json
import logging
import time
from collections import deque
from dataclasses import asdict
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from .can_id import extract
from .dashboard_config import DashboardConfig
from .dashboard_receiver import CanReceiver
from .telemetry import TelemetryStore


class DashboardBackend(QObject):
    changed = Signal()
    diagnosticsChanged = Signal()

    def __init__(self, config: DashboardConfig, parent=None, *, clock=time.monotonic):
        super().__init__(parent)
        self.config, self.clock = config, clock
        self.store = TelemetryStore(config.stale_after, clock)
        self.worker = None
        self._connection, self._detail = 'connecting', f'Opening {config.channel}…'
        self._selected = ''
        self._filter_pgn = self._filter_source = None
        self._diagnostics = deque(maxlen=200)
        self._diagnostics_paused = False
        self._frozen_rows = []
        self._rate_times = deque(maxlen=10000)
        self._started = clock()
        self._stats = {'received': 0, 'decoded_count': 0, 'malformed': 0, 'dropped': 0, 'fast_errors': {}}
        self._view = self.store.view(None, False)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    @Property(str, notify=changed)
    def channel(self):
        return self.config.channel

    @Property(str, notify=changed)
    def connection(self):
        return self._connection

    @Property(str, notify=changed)
    def connectionDetail(self):
        return self._detail

    @Property('QVariantMap', notify=changed)
    def view(self):
        return self._view

    @Property('QVariantList', notify=changed)
    def engines(self):
        return self.store.choices()

    @Property(str, notify=changed)
    def selectedKey(self):
        return self._selected

    @Property('QVariantMap', notify=changed)
    def stats(self):
        errors = self._stats['fast_errors']
        rate = self._stats.get('rate', len(self._rate_times) / min(1, max(.1, self.clock() - self._started)))
        return {**self._stats, 'transport': self.config.transport, 'host': self.config.host,
                'port': self.config.port, 'channel': self.config.channel,
                'reconnections': self._stats.get('reconnections', 0),
                'transport_errors': self._stats.get('transport_errors', 0),
                'parsing_errors': self._stats.get('parsing_errors', 0),
                'last_timestamp': self._stats.get('last_timestamp'), 'rate': rate if self._connection == 'connected' else 0,
                'fast_error_count': sum(errors.values()), 'engine_count': len(self.store.engines)}

    @Property(bool, notify=diagnosticsChanged)
    def diagnosticsPaused(self):
        return self._diagnostics_paused

    @Property('QVariantList', notify=diagnosticsChanged)
    def diagnostics(self):
        rows = self._frozen_rows if self._diagnostics_paused else self._diagnostics
        return [row for row in reversed(rows)
                if (self._filter_pgn is None or row['pgn'] == self._filter_pgn)
                and (self._filter_source is None or row['source'] == self._filter_source)]

    @Slot()
    def start(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self.worker is not None:
            self.worker.deleteLater()
        self._connection, self._detail = 'connecting', f'Opening {self.config.channel}…'
        self.store = TelemetryStore(self.config.stale_after, self.clock)
        self._selected = ''
        self._diagnostics.clear()
        self._frozen_rows = []
        self._diagnostics_paused = False
        self.diagnosticsChanged.emit()
        self._stats = {'received': 0, 'decoded_count': 0, 'malformed': 0, 'dropped': 0, 'fast_errors': {}}
        self._rate_times.clear()
        self._started = self.clock()
        self.worker = CanReceiver(self.config, self)
        self.worker.batchReceived.connect(self.on_batch)
        self.worker.connectionChanged.connect(self.on_connection)
        self.worker.start()
        self.refresh()

    @Slot(str, str)
    def on_connection(self, status, detail):
        logging.info('dashboard_can_%s channel=%s detail=%s', status, self.config.channel, detail)
        self._connection, self._detail = status, detail
        self.refresh()

    @Slot(object)
    def on_batch(self, batch):
        now = self.clock()
        try:
            decoded_count = batch.get('decoded_count', self._stats.get('decoded_count', 0) + sum(event.state is not None for event in batch['frames']))
            self._stats = {name: batch[name] for name in ('received', 'malformed', 'dropped', 'fast_errors')}
            self._stats['decoded_count'] = decoded_count
            if 'rate' in batch:
                self._stats['rate'] = batch['rate']
            for name in ('reconnections', 'transport_errors', 'parsing_errors', 'last_timestamp'):
                if name in batch:
                    self._stats[name] = batch[name]
            for event in batch['frames']:
                message = event.message
                info = None
                if message.is_extended_id and not message.is_error_frame:
                    try:
                        info = extract(message.arbitration_id)
                    except ValueError:
                        pass
                self._rate_times.append(now)
                if info and event.state is not None:
                    self.store.accept(info.source, event.state)
                decoded = asdict(event.state) if event.state is not None else None
                kind = ('malformed' if event.error else 'decoded' if decoded is not None else
                        'fragment / ignored')
                self._diagnostics.append({'id': f'{message.arbitration_id:08X}',
                    'pgn': info.pgn if info else None, 'source': info.source if info else None,
                    'timestamp': message.timestamp, 'timestamp_text': f'{message.timestamp:.6f}',
                    'payload': bytes(message.data).hex(' ').upper(),
                    'decoded': decoded, 'decoded_text': json.dumps(decoded, ensure_ascii=True) if decoded is not None else '',
                    'error': event.error, 'kind': kind, 'transport': event.transport,
                    'channel': message.channel, 'gateway_host': self.config.host,
                    'gateway_port': self.config.port if event.transport == 'socketcand' else None})
            self._choose_initial()
            if not self._diagnostics_paused:
                self.diagnosticsChanged.emit()
            self.refresh()
        finally:
            if self.worker:
                self.worker.acknowledge()

    def _choose_initial(self):
        if self._selected in self.store.engines:
            return
        self._selected = ''
        for choice in self.store.choices():
            engine = self.store.engines[choice['key']]
            if ((self.config.source_address is None or engine.source == self.config.source_address)
                    and (self.config.engine_instance is None or engine.instance == self.config.engine_instance)):
                self._selected = choice['key']
                break

    @Slot(str)
    def selectEngine(self, key):
        if key in self.store.engines:
            self._selected = key
            self.refresh()

    @Slot()
    def toggleDiagnosticsPause(self):
        self._diagnostics_paused = not self._diagnostics_paused
        self._frozen_rows = list(self._diagnostics) if self._diagnostics_paused else []
        self.diagnosticsChanged.emit()

    @Slot(str, str, result=bool)
    def filterDiagnostics(self, pgn, source):
        try:
            parsed_pgn = None if not pgn.strip() else int(pgn, 10)
            parsed_source = None if not source.strip() else int(source, 10)
            if parsed_pgn is not None and not 0 <= parsed_pgn <= 0x3ffff:
                return False
            if parsed_source is not None and not 0 <= parsed_source <= 255:
                return False
        except ValueError:
            return False
        self._filter_pgn, self._filter_source = parsed_pgn, parsed_source
        self.diagnosticsChanged.emit()
        return True

    @Slot()
    def refresh(self):
        now = self.clock()
        while self._rate_times and now - self._rate_times[0] >= 1:
            self._rate_times.popleft()
        self._view = self.store.view(self._selected, self._connection == 'connected')
        self.changed.emit()

    def snapshot(self):
        self.refresh()
        return {'channel': self.channel, 'connection': self.connection,
                'connection_detail': self.connectionDetail, 'view': self.view,
                'engines': self.engines, 'stats': self.stats, 'diagnostics': self.diagnostics}

    @Slot()
    def shutdown(self):
        self.timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            # recv uses a 50 ms timeout; never destroy a live QThread.
            self.worker.wait()
