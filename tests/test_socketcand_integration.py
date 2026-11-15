"""Real socketcand + kernel vcan + simulator; requires SOCKETCAND or PATH binary."""
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import replace
import pytest
pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QGuiApplication
from nmea_sim.dashboard_backend import DashboardBackend
from nmea_sim.dashboard_config import DashboardConfig
from nmea_sim.receiver import Decoder
from nmea_sim.can_id import extract
from test_integration_vcan import vcan, stop


@pytest.mark.vcan
def test_real_gateway_two_dashboards_restart_and_local(vcan):
    executable = os.getenv('SOCKETCAND') or shutil.which('socketcand')
    if not executable:
        pytest.skip('install socketcand or set SOCKETCAND=/path/to/socketcand')
    app = QGuiApplication.instance() or QGuiApplication([])
    # Allocate a loopback endpoint separate from operator gateways.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    config = DashboardConfig(transport='socketcand', host='127.0.0.1', port=port, stale_after=.5,
                             source_address=233)
    backends = [DashboardBackend(config), DashboardBackend(config),
                DashboardBackend(replace(config, transport='socketcan'))]
    gateways = []
    simulator = None
    def gateway():
        process = subprocess.Popen([executable, '-i', 'vcan0', '-l', 'lo', '-n', '-p', str(port)],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        gateways.append(process)
        return process
    def kill_gateway(process):
        # socketcand forks per client: restarting just the listener leaves sessions alive.
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    def wait(predicate, timeout=7):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        pytest.fail(str([(b.connection, b.connectionDetail, b.view['status'], b.stats) for b in backends]))
    try:
        first = gateway()
        for backend in backends:
            backend.start()
        wait(lambda: all(b.connection == 'connected' for b in backends))
        assert first.poll() is None
        simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator', '--channel', 'vcan0',
                                      '--source-address', '233', '--unique-number', '233',
                                      '--fault', 'low-fuel-pressure', '--fault-start', '4', '--fault-duration', '2'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def both_pgns(backend):
            return {127488, 127489} <= {r['pgn'] for r in backend.diagnostics if r['source'] == 233 and r['decoded']}
        wait(lambda: all(both_pgns(b) for b in backends))
        for backend in backends:
            assert backend.view['oil_temperature_c'] is not None
            assert backend.view['fuel_pressure_bar'] is not None
            assert backend.view['engine_load_pct'] is not None
        # Compare each client's decoded records against an independent local decoder.
        decoder = Decoder()
        expected = {}
        from dataclasses import asdict
        while (frame := vcan.recv(.02)) is not None:
            if extract(frame.arbitration_id).source == 233:
                state = decoder.receive(frame)
                if state is not None:
                    expected[(frame.arbitration_id, bytes(frame.data).hex(' ').upper())] = asdict(state)
        app.processEvents()
        for backend in backends:
            matching = 0
            for row in backend.diagnostics:
                key = (int(row['id'], 16), row['payload'])
                if row['source'] == 233 and row['decoded'] and key in expected:
                    assert row['decoded'] == expected[key]
                    matching += 1
            assert matching >= 2
        wait(lambda: all('LOW_FUEL_PRESSURE' in b.view['warnings'] for b in backends))
        assert all(b.view['fuel_pressure_bar'] == .6 for b in backends)
        wait(lambda: all(b.view['warning_known'] and not b.view['warnings'] and
                         b.view['fuel_pressure_bar'] == 3 for b in backends))
        kill_gateway(first)
        wait(lambda: all(b.connection == 'reconnecting' for b in backends[:2]))
        wait(lambda: all(b.view['rpm'] is None for b in backends[:2]))
        assert backends[2].connection == 'connected'
        previous = [b.stats['received'] for b in backends[:2]]
        second = gateway()
        # Some upstream builds enable SO_REUSEADDR only with DEBUG. Retry the
        # listener until old TCP connections leave TIME_WAIT (typically 60s).
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            app.processEvents()
            if second.poll() is not None:
                reason = second.stderr.read().decode()
                assert 'Address already in use' in reason, reason
                second = gateway()
            if all(b.connection == 'connected' for b in backends[:2]):
                break
            time.sleep(.1)
        wait(lambda: all(b.connection == 'connected' and b.stats['received'] > n
                         and b.view['status'] == 'fresh' for b, n in zip(backends[:2], previous)))
        assert second.poll() is None
        assert all(b.stats['reconnections'] >= 1 for b in backends[:2])
        assert all(b.stats['malformed'] == 0 for b in backends)
    finally:
        for backend in backends:
            backend.shutdown()
        if simulator:
            stop(simulator)
        for process in gateways:
            if process.poll() is None:
                kill_gateway(process)
