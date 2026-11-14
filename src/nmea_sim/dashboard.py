"""Native receive-only NMEA instruments. Install the optional dashboard extra."""
import json
import logging
import os
import ctypes
import signal
import sys
from pathlib import Path
from .dashboard_config import parse_dashboard_config


def platform_error(environ) -> str | None:
    platform = environ.get('QT_QPA_PLATFORM', '')
    if not platform and not environ.get('DISPLAY') and not environ.get('WAYLAND_DISPLAY'):
        return ('A Linux desktop session is required. For headless tests set '
                'QT_QPA_PLATFORM=offscreen and QT_QUICK_BACKEND=software.')
    if platform == 'xcb' or (not platform and environ.get('DISPLAY') and not environ.get('WAYLAND_DISPLAY')):
        try:
            ctypes.CDLL('libxcb-cursor.so.0')
        except OSError:
            return ('Qt X11 needs libxcb-cursor0. On Debian/Ubuntu/Parrot run: '
                    'sudo apt-get install libxcb-cursor0')
    return None


def configure_rendering(environ):
    # Use the renderer exercised by our instrument/QML tests on Linux and Pi.
    # Respect an explicit operator override for supported graphics hardware.
    environ.setdefault('QT_QUICK_BACKEND', 'software')


def main(argv=None):
    config = parse_dashboard_config(argv)
    configure_rendering(os.environ)
    try:
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickWindow  # register concrete QML window wrapper
        from PySide6.QtQuickControls2 import QQuickStyle
        from .dashboard_backend import DashboardBackend
    except ImportError:
        print("Install the native dashboard with: python -m pip install -e '.[dashboard]'", file=sys.stderr)
        return 1
    error = platform_error(os.environ)
    if error:
        print(error, file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    QQuickStyle.setStyle('Basic')
    app = QGuiApplication([sys.argv[0]])
    app.setApplicationName('NMEA Engine Instruments')
    app.setOrganizationName('NMEA Simulator Development')
    backend = DashboardBackend(config)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('dashboard', backend)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    exit_status = [0]

    def save_snapshot():
        if config.snapshot:
            config.snapshot.parent.mkdir(parents=True, exist_ok=True)
            config.snapshot.write_text(json.dumps(backend.snapshot(), indent=2, allow_nan=False) + '\n')

    def finish():
        if config.screenshot:
            config.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(config.screenshot)):
                logging.error('Could not save dashboard screenshot')
                exit_status[0] = 1
        app.quit()

    def cleanup():
        backend.shutdown()
        try:
            save_snapshot()
        except OSError as exc:
            logging.error('Cannot save diagnostic snapshot: %s', exc)
            exit_status[0] = 1

    app.aboutToQuit.connect(cleanup)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)
    QTimer.singleShot(0, backend.start)
    if config.quit_after:
        QTimer.singleShot(round(config.quit_after * 1000), finish)
    result = app.exec()
    return result or exit_status[0]


if __name__ == '__main__':
    raise SystemExit(main())
