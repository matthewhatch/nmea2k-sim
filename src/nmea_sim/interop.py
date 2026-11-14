"""Field-level comparison with independent CANboat JSON output (standard units)."""
from collections import defaultdict
import math
from .can_id import extract
from .consumer import Decoder
from . import device_protocol as p


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_canboat(frames, rows, profile: str = 'm3') -> dict:
    if profile not in ('m3', 'cycle'):
        raise ValueError('unknown capture profile')
    decoder = Decoder()
    local = defaultdict(list)
    external = defaultdict(list)
    for frame in frames:
        state = decoder.receive(frame)
        if state is not None:
            identifier = extract(frame.arbitration_id)
            local[identifier.pgn, identifier.source].append(state)
    for row in rows:
        if row.get('pgn') in p.DECODERS or row.get('pgn') in (127488, 127489):
            external[row['pgn'], row['src']].append(row)
    _require(set(local) == set(external), 'decoded PGN/source sets differ from CANboat')
    counts = defaultdict(int)
    def equal(fields, key, value, tolerance=1e-6):
        if value is None:
            _require(key not in fields or fields[key] is None, f'{key}: unsupported value fabricated')
        elif isinstance(value, (int, float)):
            observed = fields.get(key)
            if isinstance(observed, dict):
                observed = observed.get('value')
            _require(isinstance(observed, (int, float)) and math.isclose(observed, value, abs_tol=tolerance),
                     f'{key}: CANboat value differs from decoded wire value {value}')
        else:
            _require(fields.get(key) == value, f'{key}: CANboat value differs from decoded wire value')
    for key, states in local.items():
        pgn, source = key
        decoded = external[key]
        _require(len(states) == len(decoded), f'PGN {pgn}, source {source}: different message counts')
        for state, row in zip(states, decoded):
            counts[pgn] += 1
            expected_priority = 2 if pgn in (127488, 127489) else 7 if pgn == p.HEARTBEAT else 6
            _require(row['prio'] == expected_priority, f'PGN {pgn}: priority mismatch')
            fields = row['fields']
            if pgn == p.REQUEST:
                equal(fields, 'PGN', state.requested_pgn)
            elif pgn == p.CLAIM:
                equal(fields, 'Unique Number', state.unique_number)
                equal(fields, 'Device Instance Lower', state.device_instance & 7)
                equal(fields, 'Device Instance Upper', state.device_instance >> 3)
                equal(fields, 'Device Function', 'Engine')
                equal(fields, 'Device Class', 'Propulsion')
                equal(fields, 'Industry Group', 'Marine Industry')
                equal(fields, 'System Instance', state.system_instance)
                equal(fields, 'Arbitrary address capable', 'Yes')
                # CANboat treats unassigned 2046 as a numeric sentinel and omits
                # the manufacturer lookup. It must never appear as Yamaha etc.
                if state.manufacturer_code == 2046:
                    equal(fields, 'Manufacturer Code', None)
            elif pgn == p.PRODUCT:
                for wire, value in (('Model ID', state.model_id), ('Software Version Code', state.software_version),
                    ('Model Version', state.model_version), ('Model Serial Code', state.serial_code),
                    ('NMEA 2000 Version', state.nmea_version), ('Product Code', state.product_code),
                    ('Certification Level', state.certification_level), ('Load Equivalency', state.load_equivalency)):
                    equal(fields, wire, value)
            elif pgn == p.CONFIGURATION:
                for wire, value in (('Installation Description #1', state.installation_description1),
                    ('Installation Description #2', state.installation_description2),
                    ('Manufacturer Information', state.manufacturer_information)):
                    equal(fields, wire, value)
            elif pgn == p.PGN_LIST:
                equal(fields, 'Function Code', 'Transmit PGN list' if state.function == 0 else 'Receive PGN list')
                equal(fields, 'list', [{'PGN': number} for number in state.pgns])
            elif pgn == p.ACK:
                equal(fields, 'Control', 'NAK')
                equal(fields, 'PGN', state.requested_pgn)
                _require(row['dst'] == 220, 'NACK not directed to test requester')
            elif pgn == p.HEARTBEAT:
                equal(fields, 'Data transmit offset', state.interval_ms / 1000)
                equal(fields, 'Sequence Counter', state.sequence)
                equal(fields, 'Equipment Status', 'Operational')
                equal(fields, 'Controller 1 State', None)
                equal(fields, 'Controller 2 State', None)
            elif pgn == 127488:
                equal(fields, 'Instance', state.instance)
                equal(fields, 'Speed', state.rpm)
                equal(fields, 'Boost Pressure', state.boost_pa)
                equal(fields, 'Tilt/Trim', state.trim)
            elif pgn == 127489:
                equal(fields, 'Instance', state.instance)
                equal(fields, 'Oil pressure', None if state.oil_pressure_pa is None else state.oil_pressure_pa / 100000)
                equal(fields, 'Temperature', None if state.coolant_temperature_k is None else state.coolant_temperature_k - 273.15)
                equal(fields, 'Alternator Potential', state.alternator_voltage_v)
                equal(fields, 'Fuel Rate', state.fuel_rate_lph)
                equal(fields, 'Total Engine hours', None if state.engine_hours is None else state.engine_hours * 3600)
                for unsupported in ('Oil temperature', 'Coolant Pressure', 'Fuel Pressure', 'Engine Load', 'Engine Torque'):
                    equal(fields, unsupported, None)
                equal(fields, 'Discrete Status 1', [])
                equal(fields, 'Discrete Status 2', [])
    required = (*p.DECODERS, 127488, 127489) if profile == 'm3' else (127488, 127489)
    _require(all(counts[number] for number in required), f'{profile} fixture lacks a required PGN')
    if profile == 'm3':
        _require((p.CLAIM, 211) in local and (127488, 211) in local and (127489, 211) in local,
                 'fixture lacks post-conflict discovery/engine telemetry')
    engine_fields = {'rpm': (127488, 'rpm'), 'trim_pct': (127488, 'trim'),
        'oil_pressure_pa': (127489, 'oil_pressure_pa'),
        'coolant_temperature_k': (127489, 'coolant_temperature_k'),
        'alternator_voltage_v': (127489, 'alternator_voltage_v'),
        'fuel_rate_lph': (127489, 'fuel_rate_lph'), 'engine_hours': (127489, 'engine_hours')}
    ranges = {}
    for label, (pgn, attribute) in engine_fields.items():
        values = [getattr(state, attribute) for (number, _), states in local.items() if number == pgn
                  for state in states if getattr(state, attribute) is not None]
        ranges[label] = {'min': min(values), 'max': max(values)}
    return {'profile': profile, 'messages_compared': sum(counts.values()),
            'per_pgn': dict(sorted(counts.items())), 'engine_ranges': ranges}
