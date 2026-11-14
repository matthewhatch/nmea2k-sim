#!/usr/bin/env python3
"""Capture a bounded demo through candump, on vcan0 only. Run from repo root."""
import argparse
import subprocess
import sys
import time
from pathlib import Path
from nmea_sim.config import Config
from nmea_sim.transport import is_virtual_can, open_bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('docs/captures/engine-default.log'))
    args = parser.parse_args()
    if not is_virtual_can('vcan0'):
        parser.error('vcan0 must be a kernel virtual CAN interface')
    # Check accessibility before starting candump; never configure an interface.
    with open_bus(Config('vcan0', 205)):
        pass
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w') as output:
        capture = subprocess.Popen(['candump', '-L', '-n', '113',
            'vcan0,09F200CD:1FFFFFFF,09F201CD:1FFFFFFF'], stdout=output, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(.2)  # allow candump to bind; missing frames cause explicit failure below
            if capture.poll() is not None:
                raise RuntimeError('candump exited before simulation started')
            subprocess.run([sys.executable, '-m', 'nmea_sim.simulator', '--channel', 'vcan0',
                '--source-address', '205', '--unique-number', '205', '--rapid-hz', '5', '--dynamic-hz', '1', '--count', '61'],
                check=True, timeout=18)
            _, stderr = capture.communicate(timeout=3)
            if capture.returncode:
                raise RuntimeError(stderr)
        finally:
            if capture.poll() is None:
                capture.terminate()
                capture.wait(timeout=3)
    if len(args.output.read_text().splitlines()) != 113:
        raise RuntimeError('incomplete capture; reserve source 205 and retry')
    print(f'Captured 113 real CAN frames to {args.output}')


if __name__ == '__main__':
    main()
