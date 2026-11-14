"""Claim an address, serve discovery, and publish engine telemetry over CAN."""
import logging
import time
from dataclasses import replace
import can
from .config import parse_config, stable_unique_number
from .transport import open_bus
from .can_id import compose
from .engine_model import sample, sample_dynamic
from . import pgn_127488, pgn_127489
from .device import Device
from .device_protocol import Name


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = parse_config(argv)
    try:
        name = Name(stable_unique_number(config), config.manufacturer_code,
                    config.device_instance, system_instance=config.system_instance)
        device = Device(name, config.source_address)
        with open_bus(config, transmit=True) as bus:
            def transmit(frames):
                for frame in frames:
                    bus.send(can.Message(arbitration_id=compose(frame.pgn, frame.source,
                        frame.priority, frame.destination), is_extended_id=True, data=frame.data), timeout=1)

            transmit(device.start(time.monotonic()))
            logging.info('claiming address=%d name=%016x', device.address, name.value)
            model_start = None
            rapid_deadline = dynamic_deadline = None
            count = rapid_tick = dynamic_tick = 0
            schedule_start = 0.0
            while config.count is None or count < config.count:
                now = time.monotonic()
                transmit(device.tick(now))
                if device.owns_address:
                    if rapid_deadline is None:
                        if model_start is None:
                            model_start = now
                        schedule_start = now
                        rapid_deadline = dynamic_deadline = now
                        rapid_tick = dynamic_tick = 0
                        logging.info('address_owned address=%d', device.address)
                    if now >= rapid_deadline:
                        state = replace(sample(now - model_start), instance=config.engine_instance)
                        transmit(device.engine_message(pgn_127488.PGN, pgn_127488.encode(state)))
                        count += 1
                        rapid_tick += 1
                        rapid_deadline = schedule_start + rapid_tick / config.rapid_hz
                        if rapid_deadline <= now:
                            rapid_deadline = now + 1 / config.rapid_hz
                    if now >= dynamic_deadline:
                        state = replace(sample_dynamic(now - model_start), instance=config.engine_instance)
                        transmit(device.engine_message(pgn_127489.PGN, pgn_127489.encode(state)))
                        dynamic_tick += 1
                        dynamic_deadline = schedule_start + dynamic_tick / config.dynamic_hz
                        if dynamic_deadline <= now:
                            dynamic_deadline = now + 1 / config.dynamic_hz
                else:
                    rapid_deadline = dynamic_deadline = None
                if config.count is not None and count >= config.count:
                    break
                # Short CAN receive waits keep conflicts/requests responsive without
                # another thread or reader competing for the simulator's socket.
                wake = min(now + .05, device.heartbeat_deadline)
                if device.owns_address:
                    wake = min(wake, rapid_deadline, dynamic_deadline)
                elif device.state == 'claiming':
                    wake = min(wake, device.claim_deadline)
                message = bus.recv(max(0, wake - time.monotonic()))
                if message is not None:
                    old_address = device.address
                    transmit(device.receive(message, time.monotonic()))
                    if not device.owns_address:
                        rapid_deadline = dynamic_deadline = None
                    if old_address != device.address:
                        logging.warning('address_conflict old=%d new=%d', old_address, device.address)
                    if device.state == 'cannot_claim':
                        raise ValueError('No free CAN source address; telemetry stopped')
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, can.CanError) as exc:
        logging.error('%s', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
