#!/usr/bin/env python3
"""Capture an M7 pressure fault on verified vcan0; reserves source/NAME 238."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from nmea_sim.config import Config
from nmea_sim.transport import open_bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('docs/captures/m7-fault.log'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples = []
    raw = bytearray()
    # Test identity 2046 enforces a verified kernel-vcan interface.
    with open_bus(Config('vcan0', 238), transmit=True) as bus, args.output.open('w') as output:
        process = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator',
            '--channel', 'vcan0', '--source-address', '238', '--unique-number', '238', '--count', '41',
            '--fault', 'low-fuel-pressure', '--fault-start', '4', '--fault-duration', '2'],
            stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                message = bus.recv(.1)
                if message is None:
                    if process.poll() is not None:
                        break
                    continue
                if message.arbitration_id & 255 != 238:
                    continue
                output.write(f'({message.timestamp:.6f}) vcan0 {message.arbitration_id:08X}#{bytes(message.data).hex().upper()}\n')
                if (message.arbitration_id >> 8) & 0x3ffff != 127489:
                    continue
                frame = bytes(message.data)
                if frame[0] & 31 == 0:
                    assert frame[1] == 26
                    raw = bytearray(frame[2:])
                else:
                    raw.extend(frame[1:])
                if len(raw) >= 26:
                    # Independent fast-packet assembly and field offsets.
                    samples.append({'oil_temperature_k': int.from_bytes(raw[3:5], 'little') * .1,
                        'fuel_pressure_pa': int.from_bytes(raw[17:19], 'little') * 1000,
                        'status1': int.from_bytes(raw[20:22], 'little'), 'engine_load_pct': raw[24]})
                    raw.clear()
            _, log = process.communicate(timeout=2)
            if process.returncode:
                raise RuntimeError(log)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
    assert len(samples) == 9, f'expected 9 dynamic messages, received {len(samples)}'
    active = [i for i, s in enumerate(samples) if s['status1'] & 16]
    assert active == [4, 5], active
    assert all(samples[i]['fuel_pressure_pa'] == 60000 for i in active)
    assert 100000 < samples[3]['fuel_pressure_pa'] < 250000  # cranking before the fault
    assert samples[6]['fuel_pressure_pa'] == 300000
    assert all(293 <= s['oil_temperature_k'] < 374 and 0 <= s['engine_load_pct'] <= 85 for s in samples)
    report = args.output.with_suffix('.json')
    report.write_text(json.dumps({'scenario': 'low-fuel-pressure', 'start': 4,
        'duration': 2, 'samples': samples}, indent=2) + '\n')
    print(f'Verified activation, recovery and {len(samples)} dynamic samples: {args.output}, {report}')


if __name__ == '__main__':
    main()
