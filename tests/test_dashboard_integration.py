"""Native offscreen Qt application and simulator communicate only through vcan0."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
pytest.importorskip('PySide6')
from test_integration_vcan import vcan, stop, wait_until


def qt_environment():
    return {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
            'NMEA_CAN_CHANNEL': 'missing0'}


@pytest.mark.vcan
@pytest.mark.parametrize('stale', [False, True])
def test_dashboard_and_simulator_independent_processes(vcan, tmp_path, stale):
    source = 235 if not stale else 236
    report = tmp_path / 'dashboard.json'
    image = tmp_path / 'dashboard.png'
    log = tmp_path / 'dashboard.stderr'
    command = [sys.executable, '-m', 'nmea_sim.dashboard', '--channel', 'vcan0',
        '--source-address', str(source), '--engine-instance', '1',
        '--stale-after', '.5' if stale else '1.5', '--quit-after', '3' if stale else '4.2',
        '--snapshot', str(report), '--screenshot', str(image)]
    with log.open('w') as stderr:
        dashboard = subprocess.Popen(command, env=qt_environment(), stderr=stderr, text=True)
    simulator = None
    try:
        wait_until(lambda: 'dashboard_can_connected channel=vcan0' in log.read_text())
        simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator',
            '--channel', 'vcan0', '--source-address', str(source), '--unique-number', str(source),
            '--engine-instance', '1', '--count', '6' if stale else '16'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dashboard.wait(timeout=9)
        assert dashboard.returncode == 0, log.read_text()
        _, stderr = simulator.communicate(timeout=5)
        assert simulator.returncode == 0, stderr
        state = json.loads(report.read_text())
        assert state['channel'] == 'vcan0' and state['connection'] == 'connected'
        assert state['view']['source'] == source and state['view']['instance'] == 1
        assert state['stats']['received'] >= 16
        assert state['stats']['malformed'] == 0
        assert state['stats']['fast_error_count'] == 0
        assert image.read_bytes().startswith(b'\x89PNG')
        if stale:
            assert state['view']['status'] == 'stale'
            assert state['view']['rpm'] is None and state['view']['voltage_v'] is None
            assert state['view']['running'] == 'Unknown'
        else:
            assert state['view']['status'] == 'fresh'
            assert state['view']['rpm'] > 0 and state['view']['temperature_c'] >= 20
            assert state['view']['engine_hours'] >= 100
            matching = [row for row in state['diagnostics'] if row['source'] == source and row['pgn'] == 127488]
            assert matching[0]['decoded']['rpm'] == state['view']['rpm']
            assert matching[0]['payload'] and matching[0]['id'] == f'09F200{source:02X}'
        assert 'ReferenceError' not in log.read_text() and 'failed to load component' not in log.read_text()
    finally:
        stop(dashboard)
        if simulator is not None:
            stop(simulator)


def test_native_application_survives_missing_interface(tmp_path):
    report = tmp_path / 'absent.json'
    result = subprocess.run([sys.executable, '-m', 'nmea_sim.dashboard', '--channel', 'absent0',
        '--quit-after', '.4', '--snapshot', str(report)], env=qt_environment(), capture_output=True,
        text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    state = json.loads(report.read_text())
    assert state['connection'] == 'error' and 'does not exist' in state['connection_detail']
    assert state['view']['rpm'] is None



def test_instruments_render_without_simulator_or_renderer_override(tmp_path):
    from PySide6.QtGui import QImage
    image_path = tmp_path / 'instruments.png'
    environment = qt_environment()
    environment.pop('QT_QUICK_BACKEND', None)
    result = subprocess.run([sys.executable, '-m', 'nmea_sim.dashboard', '--channel', 'absent0',
        '--quit-after', '.6', '--screenshot', str(image_path)], env=environment,
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    image = QImage(str(image_path))
    assert not image.isNull()
    assert image.pixelColor(10, 2).name() == '#55e3cc'
    colors = {image.pixelColor(x, y).rgba() for x in range(20, image.width(), 10)
              for y in range(20, image.height(), 10)}
    assert len(colors) > 20, 'blank scene: instruments must render even without CAN data'
