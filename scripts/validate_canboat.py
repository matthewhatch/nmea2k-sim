#!/usr/bin/env python3
"""Run independently built CANboat against a real CAN capture and compare fields."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from nmea_sim.capture import read_candump
from nmea_sim.interop import validate_canboat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyzer', required=True, type=Path)
    parser.add_argument('--converter', required=True, type=Path)
    parser.add_argument('--capture', type=Path, default=Path('docs/captures/m3-device.log'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile', choices=('m3', 'cycle'), default='m3')
    parser.add_argument('--canboat-revision', help='optional source commit recorded as supplied by the operator')
    args = parser.parse_args()
    if args.output is None:
        args.output = args.capture.with_suffix('.canboat.jsonl')
    converted = subprocess.run([str(args.converter.resolve()), str(args.capture.resolve())],
                               check=True, capture_output=True, text=True, timeout=30)
    flags = ['-json', '-nv'] if args.profile == 'cycle' else ['-json']
    analyzed = subprocess.run([str(args.analyzer.resolve()), *flags], input=converted.stdout,
                             check=True, capture_output=True, text=True, timeout=30)
    rows = [json.loads(line) for line in analyzed.stdout.splitlines()]
    result = validate_canboat(read_candump(args.capture), rows, args.profile)
    args.output.write_text(analyzed.stdout)
    result['canboat_version'] = rows[0]['version']
    result['analyzer_sha256'] = hashlib.sha256(args.analyzer.read_bytes()).hexdigest()
    result['converter_sha256'] = hashlib.sha256(args.converter.read_bytes()).hexdigest()
    result['decoded_sha256'] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    if args.canboat_revision:
        result['canboat_revision'] = args.canboat_revision
    result['capture_sha256'] = hashlib.sha256(args.capture.read_bytes()).hexdigest()
    args.output.with_suffix('.validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
