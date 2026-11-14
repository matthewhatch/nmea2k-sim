#!/usr/bin/env python3
"""Record real vcan-only M3 discovery, negative requests, conflicts and heartbeat.

Reserves source addresses 210, 211 and 220. Does not configure any interface.
"""
import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
import can
from nmea_sim.config import Config
from nmea_sim.transport import open_bus
from nmea_sim.consumer import Decoder


def identifier(pgn, source, destination=255):
    # Independent test-peer identifier composition; no device implementation calls.
    return (6 << 26) | (pgn << 8) | source | (destination << 8 if (pgn >> 8) & 255 < 240 else 0)


def peer_name(unique, instance=0):
    return (unique | 2046 << 21 | instance << 32 | 140 << 40 | 50 << 49 | 4 << 60 | 1 << 63).to_bytes(8, 'little')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('docs/captures/m3-device.log'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    events = []
    capture = simulator = None
    with open_bus(Config('vcan0', 220), transmit=True) as bus, args.output.open('w') as output:
        decoder = Decoder()
        def send(pgn, data, source=220, destination=255):
            bus.send(can.Message(arbitration_id=identifier(pgn, source, destination),
                                 is_extended_id=True, data=data), timeout=1)
        def wait_for(pgn, source, predicate=lambda state: True, timeout=4):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                frame = bus.recv(max(0, deadline - time.monotonic()))
                if frame is None:
                    break
                wire_pgn = (frame.arbitration_id >> 8) & 0x3ffff
                if (wire_pgn >> 8) & 255 < 240:
                    wire_pgn &= ~255
                if wire_pgn != pgn or frame.arbitration_id & 255 != source:
                    continue
                state = decoder.receive(frame)
                if state is not None and predicate(state):
                    return frame, state
            raise RuntimeError(f'timed out waiting for PGN {pgn}, source {source}')
        def assert_silent(pgn, source, seconds=.15):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                frame = bus.recv(deadline - time.monotonic())
                if frame is None:
                    break
                received_pgn = (frame.arbitration_id >> 8) & 0x3ffff
                if (received_pgn >> 8) & 255 < 240:
                    received_pgn &= ~255
                if frame.arbitration_id & 255 == source and received_pgn == pgn:
                    raise RuntimeError('unexpected response to an ignored request')
        try:
            capture = subprocess.Popen(['candump', '-L',
                'vcan0,000000D2:000000FF,000000D3:000000FF,000000DC:000000FF'],
                stdout=output, stderr=subprocess.PIPE, text=True)
            time.sleep(.2)
            if capture.poll() is not None:
                raise RuntimeError('candump failed to bind')
            send(60928, peer_name(220))  # test requester claims its own address
            time.sleep(.25)
            simulator = subprocess.Popen([sys.executable, '-m', 'nmea_sim.simulator',
                '--channel', 'vcan0', '--source-address', '210', '--unique-number', '210',
                '--manufacturer-code', '2046', '--device-instance', '17', '--system-instance', '0',
                '--engine-instance', '2', '--rapid-hz', '5', '--dynamic-hz', '1'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            claim, _ = wait_for(60928, 210)
            first, state = wait_for(127488, 210)
            if first.timestamp - claim.timestamp < .24 or state.instance != 2:
                raise RuntimeError('claim gating or engine-instance mismatch')
            events.append('claim then >=250ms wait before engine TX, instance 2')
            for destination in (210, 255):
                for requested in (60928, 126996, 126998, 126464):
                    send(59904, requested.to_bytes(3, 'little'), destination=destination)
                    wait_for(requested, 210)
                    if requested == 126464:
                        wait_for(requested, 210, lambda state: state.function == 1)
                    events.append(f'ISO request {requested} destination {destination}: response decoded')
            for requested in (127508, 126993):
                send(59904, requested.to_bytes(3, 'little'), destination=210)
                wait_for(59392, 210, lambda state: state.control == 1 and state.requested_pgn == requested)
                events.append(f'directed {requested}: NACK')
            send(59904, (127508).to_bytes(3, 'little'))
            assert_silent(59392, 210)
            send(59904, (126996).to_bytes(3, 'little'), destination=209)
            assert_silent(126996, 210)
            events.append('unsupported global and other-destination requests: no response')
            send(60928, peer_name(211, 18), source=210)  # our NAME wins
            reclaim, _ = wait_for(60928, 210)
            resumed, _ = wait_for(127488, 210)
            if resumed.timestamp - reclaim.timestamp < .24:
                raise RuntimeError('winning conflict did not gate telemetry')
            send(60928, peer_name(209, 16), source=210)  # peer wins; move to 211
            moved, _ = wait_for(60928, 211)
            resumed, _ = wait_for(127488, 211)
            if resumed.timestamp - moved.timestamp < .24:
                raise RuntimeError('losing conflict did not gate telemetry')
            events.append('winning conflict reasserted 210; losing conflict moved to 211; both gated')
            send(59904, (126996).to_bytes(3, 'little'), destination=211)
            wait_for(126996, 211)
            wait_for(126993, 211, timeout=7)
            events.append('identity request and periodic heartbeat received at new source 211')
            simulator.send_signal(signal.SIGINT)
            simulator.communicate(timeout=3)
            if simulator.returncode:
                raise RuntimeError('simulator failed')
        finally:
            for process in (simulator, capture):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    args.output.with_suffix('.events.json').write_text(json.dumps(events, indent=2) + '\n')
    print(f'Recorded {len(events)} protocol checks to {args.output}')


if __name__ == '__main__':
    main()
