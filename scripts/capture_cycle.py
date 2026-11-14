#!/usr/bin/env python3
"""Capture a complete engine cycle on verified virtual CAN only (about 52 seconds)."""
import argparse
import subprocess
import sys
import time
from pathlib import Path
from nmea_sim.config import Config
from nmea_sim.transport import open_bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', default='vcan0')
    parser.add_argument('--output', type=Path, default=Path('docs/captures/m4-cycle.log'))
    args = parser.parse_args()
    # Manufacturer 2046 requires verified kernel-vcan even with physical opt-in.
    with open_bus(Config(args.channel, 230), transmit=True):
        pass
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w') as output:
        capture = subprocess.Popen(['candump', '-L', '-n', '464',
            f'{args.channel},09F200E6:1FFFFFFF,09F201E6:1FFFFFFF'],
            stdout=output, stderr=subprocess.PIPE, text=True)
        simulator = None
        try:
            time.sleep(.2)
            if capture.poll() is not None:
                raise RuntimeError('candump exited before simulation started')
            simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator',
                '--channel', args.channel, '--source-address', '230', '--unique-number', '230',
                '--manufacturer-code', '2046', '--engine-instance', '1', '--device-instance', '2',
                '--system-instance', '1', '--rapid-hz', '5', '--dynamic-hz', '1', '--count', '256'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            _, stderr = simulator.communicate(timeout=57)
            if simulator.returncode:
                raise RuntimeError(f'simulator failed: {stderr}')
            _, stderr = capture.communicate(timeout=3)
            if capture.returncode:
                raise RuntimeError(f'candump failed: {stderr}')
        finally:
            for process in (simulator, capture):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    count = len(args.output.read_text().splitlines())
    if count != 464:
        raise RuntimeError(f'incomplete capture ({count} frames); reserve source 230 and retry')
    print(f'Captured {count} real frames over 51 seconds to {args.output}')


if __name__ == '__main__':
    main()
