from dataclasses import replace
import pytest
from nmea_sim.config import parse_config
from nmea_sim.engine_model import sample_dynamic
from nmea_sim.faults import FaultScenario
from nmea_sim.pgn_127489 import Status1, encode
from nmea_sim.fast_packet import fragment
from nmea_sim.receiver import Decoder
from nmea_sim.can_id import compose
import can


@pytest.mark.parametrize('args', [
    ['--fault', 'unknown'], ['--fault-start', '-1'], ['--fault-start', 'nan'],
    ['--fault-duration', '0'], ['--fault-duration', 'inf'],
    ['--fault-start', '1e308', '--fault-duration', '1e308'],
])
def test_invalid_fault_config(args):
    with pytest.raises(SystemExit):
        parse_config(args)


@pytest.mark.parametrize('name,field,bit', [
    ('low-oil-pressure', 'oil_pressure_pa', Status1.LOW_OIL_PRESSURE),
    ('low-fuel-pressure', 'fuel_pressure_pa', Status1.LOW_FUEL_PRESSURE),
    ('charging-failure', 'alternator_voltage_v', Status1.CHARGE_INDICATOR),
])
def test_fault_interval_and_recovery(name, field, bit):
    fault = FaultScenario(name, 20, 10)
    assert sample_dynamic(19.999, fault) == sample_dynamic(19.999)
    nominal = sample_dynamic(20)
    affected = sample_dynamic(20, fault)
    assert getattr(affected, field) < getattr(nominal, field)
    assert affected.status1 & bit
    assert affected.engine_load_pct == nominal.engine_load_pct
    assert affected.fuel_rate_lph == nominal.fuel_rate_lph
    assert sample_dynamic(30, fault) == sample_dynamic(30)
    assert sample_dynamic(70, fault) == sample_dynamic(70)  # no cycle repeat
    baseline = replace(nominal, status1=Status1.WATER_IN_FUEL, status2=8)
    result = fault.apply(baseline, 25, True)
    assert result.status1 & Status1.WATER_IN_FUEL and result.status2 == 8


def test_charging_failure_stages():
    fault = FaultScenario('charging-failure', 20, 10)
    assert not sample_dynamic(20, fault).status1 & Status1.LOW_SYSTEM_VOLTAGE
    assert sample_dynamic(29, fault).status1 & Status1.LOW_SYSTEM_VOLTAGE


@pytest.mark.parametrize('name', ['low-oil-pressure', 'low-fuel-pressure', 'charging-failure', 'overheating'])
def test_fault_suppressed_when_stopped(name):
    fault = FaultScenario(name, 0, 2)
    assert sample_dynamic(1, fault) == sample_dynamic(1)


def test_overheating_has_continuous_recovery_and_retained_heat():
    fault = FaultScenario('overheating', 20, 10)
    assert sample_dynamic(20, fault).coolant_temperature_k == sample_dynamic(20).coolant_temperature_k
    assert sample_dynamic(29, fault).status1 & Status1.OVER_TEMPERATURE
    at_end = sample_dynamic(30, fault)
    assert not at_end.status1
    assert at_end.coolant_temperature_k > sample_dynamic(30).coolant_temperature_k + 60
    assert abs(at_end.coolant_temperature_k - sample_dynamic(29.999, fault).coolant_temperature_k) < .1
    assert sample_dynamic(50, fault).coolant_temperature_k > sample_dynamic(50).coolant_temperature_k


def test_new_measurements_and_fault_survive_wire_transport():
    expected = sample_dynamic(25, FaultScenario('low-fuel-pressure'))
    decoder = Decoder()
    result = None
    for payload in fragment(encode(expected), 0):
        result = decoder.receive(can.Message(arbitration_id=compose(127489, 35),
                                            is_extended_id=True, data=payload))
    assert result.oil_temperature_k == pytest.approx(expected.oil_temperature_k, abs=.05)
    assert result.fuel_pressure_pa == 60000
    assert result.engine_load_pct == 85
    assert result.status1 & Status1.LOW_FUEL_PRESSURE
    # Independent wire offsets verify the newly populated fields.
    payload = encode(expected)
    assert int.from_bytes(payload[3:5], 'little') * .1 == pytest.approx(expected.oil_temperature_k, abs=.05)
    assert int.from_bytes(payload[17:19], 'little') * 1000 == 60000
    assert payload[24] == 85
