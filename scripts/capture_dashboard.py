#!/usr/bin/env python3
"""Capture native instruments fed by an independent simulator over vcan0 only."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def stop(process):
    if process and process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('docs/captures'))
    parser.add_argument('--platform', choices=('offscreen', 'xcb'), default='offscreen')
    parser.add_argument('--duration', type=float, default=15)
    args = parser.parse_args()
    if not 5 <= args.duration <= 60:
        parser.error('duration must be 5–60 seconds')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = args.output_dir / 'm5-dashboard-live.json'
    screenshot = args.output_dir / 'm5-dashboard-live.png'
    env = {**os.environ, 'QT_QPA_PLATFORM': args.platform, 'QT_QUICK_BACKEND': 'software'}
    simulator = dashboard = None
    with tempfile.TemporaryFile(mode='w+t') as log:
        try:
            dashboard = subprocess.Popen([sys.executable, '-m', 'nmea_sim.dashboard', '--channel', 'vcan0',
                '--source-address', '237', '--engine-instance', '1', '--quit-after', str(args.duration),
                '--snapshot', str(report), '--screenshot', str(screenshot)], stderr=log, env=env)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                log.seek(0)
                text = log.read()
                if 'dashboard_can_connected channel=vcan0' in text:
                    break
                if dashboard.poll() is not None or 'dashboard_can_error' in text:
                    raise RuntimeError(text)
                time.sleep(.05)
            else:
                raise RuntimeError('dashboard did not open vcan0')
            simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator', '--channel', 'vcan0',
                '--source-address', '237', '--unique-number', '237', '--engine-instance', '1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            dashboard.wait(timeout=args.duration + 5)
            if dashboard.returncode:
                log.seek(0)
                raise RuntimeError(log.read())
            state = json.loads(report.read_text())
            if state['view']['status'] != 'fresh' or state['view']['source'] != 237:
                raise RuntimeError('capture lacks fresh independent CAN engine data')
            print(f"Native {args.platform} screenshot: {screenshot}; RPM={state['view']['rpm']}, "
                  f"temperature={state['view']['temperature_c']:.2f} C, source={state['view']['source']}")
        finally:
            stop(dashboard)
            stop(simulator)


if __name__ == '__main__':
    main()
