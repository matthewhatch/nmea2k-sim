import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
import json
from dataclasses import replace
from pathlib import Path
import can
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QUrl, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from nmea_sim.dashboard_backend import DashboardBackend
from nmea_sim.dashboard_config import DashboardConfig
from nmea_sim.dashboard_receiver import ReceivedFrame, CanReceiver
from nmea_sim.receiver import Decoder
from nmea_sim.fast_packet import fragment
from nmea_sim.can_id import compose
from nmea_sim.pgn_127488 import RapidUpdate, encode as encode_rapid
from nmea_sim.pgn_127489 import DynamicUpdate, encode as encode_dynamic


@pytest.fixture(scope='module')
def app():
    instance = QGuiApplication.instance() or QGuiApplication([])
    return instance


def packet(pgn, payload, source=35):
    return can.Message(arbitration_id=compose(pgn, source), is_extended_id=True, data=payload, timestamp=123.5)


def batch(events, **kwargs):
    return {'frames': events, 'received': len(events), 'malformed': 0, 'dropped': 0, 'fast_errors': {}, **kwargs}


def test_native_qml_gauge_and_fast_packet_updates(app):
    config = DashboardConfig()
    backend = DashboardBackend(config)
    backend.on_connection('connected', 'test virtual input')
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('dashboard', backend)
    qml = Path(__file__).resolve().parents[1] / 'src/nmea_sim/qml/Main.qml'
    engine.load(QUrl.fromLocalFile(str(qml)))
    assert engine.rootObjects()
    root = engine.rootObjects()[0]
    try:
        decoder = Decoder()
        message = packet(127488, encode_rapid(RapidUpdate(0, 3000, None, -4)))
        backend.on_batch(batch([ReceivedFrame(message, decoder.receive(message))]))
        app.processEvents()
        gauge = root.findChild(QObject, 'rpmGauge')
        assert gauge.property('reading') == 3000
        assert backend.view['temperature_c'] is None
        payload = encode_dynamic(DynamicUpdate(coolant_temperature_k=353.15, alternator_voltage_v=14.2))
        frames = fragment(payload, 0)
        for data in frames[:-1]:
            message = packet(127489, data)
            backend.on_batch(batch([ReceivedFrame(message, decoder.receive(message))]))
        assert backend.view['temperature_c'] is None
        message = packet(127489, frames[-1])
        backend.on_batch(batch([ReceivedFrame(message, decoder.receive(message))]))
        app.processEvents()
        assert root.findChild(QObject, 'temperatureGauge').property('reading') == pytest.approx(80)
        assert gauge.property('reading') == 3000
        assert backend.view['status'] == 'fresh'
        QTest.qWait(350)
        assert gauge.property('displayed') == pytest.approx(3000, abs=1)
        assert root.grabWindow().width() == 1280
        root.setProperty('diagnosticsOpen', True)
        QTest.qWait(50)
        assert root.findChild(QObject, 'diagnosticList').property('count') == 5
    finally:
        backend.shutdown()
        root.close()
        del engine


def test_diagnostic_filters_and_bounded_storage(app):
    backend = DashboardBackend(DashboardConfig())
    decoder = Decoder()
    for i in range(220):
        source = 35 if i % 2 else 36
        message = packet(127488, encode_rapid(RapidUpdate(0, i, None, -4)), source)
        backend.on_batch(batch([ReceivedFrame(message, decoder.receive(message))]))
    assert len(backend.diagnostics) == 200
    assert backend.filterDiagnostics('127488', '35')
    assert len(backend.diagnostics) == 100
    assert all(row['source'] == 35 and row['payload'] and row['decoded']['rpm'] is not None
               for row in backend.diagnostics)
    assert not backend.filterDiagnostics('bad', '')
    backend.selectEngine('36:0')
    assert backend.view['source'] == 36
    backend.shutdown()


def test_qt_stale_timer_and_unknown_alerts(app):
    now = [0.0]
    backend = DashboardBackend(DashboardConfig(stale_after=1), clock=lambda: now[0])
    backend.on_connection('connected', 'test')
    message = packet(127488, encode_rapid(RapidUpdate(0, 750, None, -4)))
    backend.on_batch(batch([ReceivedFrame(message, Decoder().receive(message))]))
    assert backend.view['rpm'] == 750
    now[0] = 1
    backend.refresh()
    assert backend.view['status'] == 'stale' and backend.view['rpm'] is None
    assert backend.view['low_voltage'] is None
    backend.shutdown()


def test_worker_failure_does_not_transmit(app, monkeypatch):
    def fail(config, *, transmit=False):
        assert transmit is False
        raise ValueError('interface absent')
    monkeypatch.setattr('nmea_sim.dashboard_receiver.open_receive_transport', fail)
    receiver = CanReceiver('absent0')
    errors = []
    receiver.connectionChanged.connect(lambda *args: errors.append(args))
    receiver.start()
    assert receiver.wait(2000)
    app.processEvents()
    assert errors[-1] == ('error', 'interface absent')
    assert errors[0][0] == 'connecting'


def test_diagnostic_pause_keeps_receiving_engine_updates(app):
    backend = DashboardBackend(DashboardConfig())
    backend.on_connection('connected', 'test')
    decoder = Decoder()
    for rpm in (750, 1500):
        message = packet(127488, encode_rapid(RapidUpdate(0, rpm, None, -4)))
        backend.on_batch(batch([ReceivedFrame(message, decoder.receive(message))]))
        if rpm == 750:
            backend.toggleDiagnosticsPause()
    assert backend.diagnosticsPaused
    assert backend.diagnostics[0]['decoded']['rpm'] == 750
    assert backend.view['rpm'] == 1500
    backend.toggleDiagnosticsPause()
    assert backend.diagnostics[0]['decoded']['rpm'] == 1500
    backend.shutdown()


def test_worker_rejects_malformed_and_tracks_reassembly_errors(app, monkeypatch):
    import time
    from collections import deque
    from PySide6.QtTest import QSignalSpy
    frames = deque([packet(127488, bytes(7)), packet(127489, b'\x01' + bytes(7))])
    class Bus:
        def close(self):
            pass
        def recv(self, timeout):
            if frames:
                return frames.popleft()
            time.sleep(.01)
    monkeypatch.setattr('nmea_sim.dashboard_receiver.open_receive_transport', lambda *args, **kwargs: Bus())
    receiver = CanReceiver('vcan0')
    spy = QSignalSpy(receiver.batchReceived)
    receiver.start()
    try:
        deadline = time.monotonic() + 2
        while not spy.count() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert spy.count()
        result = spy.at(0)[0]
        assert result['malformed'] == 1 and result['decoded_count'] == 0
        assert result['fast_errors']['orphan_frame'] == 1
        assert result['frames'][0].error and result['frames'][0].state is None
    finally:
        receiver.stop()
        assert receiver.wait(2000)


def test_worker_bounds_ui_backlog_and_shutdown(app, monkeypatch):
    import time
    from PySide6.QtTest import QSignalSpy
    closed = []
    class Flood:
        def recv(self, timeout):
            return packet(127488, encode_rapid(RapidUpdate(0, 750, None, 0)))
        def close(self):
            closed.append(True)
    monkeypatch.setattr('nmea_sim.dashboard_receiver.open_receive_transport', lambda config: Flood())
    receiver = CanReceiver('vcan0')
    spy = QSignalSpy(receiver.batchReceived)
    receiver.start()
    try:
        time.sleep(.25)  # main thread deliberately does not acknowledge batches
        app.processEvents()
        assert spy.count() == 1
        assert len(spy.at(0)[0]['frames']) <= 256
        assert spy.at(0)[0]['dropped'] > 0
        receiver.acknowledge()
        time.sleep(.1)
        app.processEvents()
        assert spy.count() == 2
        assert len(spy.at(1)[0]['frames']) <= 256
    finally:
        receiver.stop()
        assert receiver.wait(1500)
    assert closed == [True]


def test_stop_during_remote_retry(app, monkeypatch):
    from PySide6.QtTest import QSignalSpy
    def fail(config):
        raise ConnectionError('offline')
    monkeypatch.setattr('nmea_sim.dashboard_receiver.open_receive_transport', fail)
    receiver = CanReceiver(DashboardConfig(transport='socketcand', host='localhost'))
    spy = QSignalSpy(receiver.connectionChanged)
    receiver.start()
    QTest.qWait(100)
    receiver.stop()
    assert receiver.wait(1000)
    app.processEvents()
    states = [spy.at(i)[0] for i in range(spy.count())]
    assert states[:3] == ['connecting', 'error', 'reconnecting']
    assert states[-1] == 'disconnected'
