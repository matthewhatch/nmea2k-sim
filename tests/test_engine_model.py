import pytest
from nmea_sim.engine_model import sample, sample_dynamic, state_at, Phase


@pytest.mark.parametrize('t,phase,rpm', [(0, Phase.OFF, 0), (2, Phase.STARTING, 0),
    (3, Phase.STARTING, 375), (4, Phase.IDLE, 750), (9, Phase.ACCELERATION, 750),
    (14, Phase.ACCELERATION, 2625), (19, Phase.CRUISE, 4500),
    (29, Phase.DECELERATION, 4500), (34, Phase.DECELERATION, 2625),
    (39, Phase.IDLE, 750), (44, Phase.DECELERATION, 750), (46, Phase.OFF, 0)])
def test_phases(t, phase, rpm):
    assert state_at(t).phase == phase
    assert sample(t).rpm == rpm
    assert sample(t) == sample(t + 50)
    assert sample(t).boost_pa is None


@pytest.mark.parametrize('boundary', [2, 4, 9, 19, 29, 39, 44, 46, 50])
def test_smooth(boundary):
    assert abs(sample(boundary - .001).rpm - sample(boundary + .001).rpm) < .001


@pytest.mark.parametrize('t', [-1, float('nan'), float('inf')])
def test_invalid(t):
    with pytest.raises(ValueError):
        sample(t)


def test_off_sensors_and_running_time():
    assert sample_dynamic(0).fuel_rate_lph == 0
    assert sample_dynamic(0).oil_pressure_pa == 0
    assert sample_dynamic(0).alternator_voltage_v == 12.6
    assert sample_dynamic(5).alternator_voltage_v == 14.2
    assert state_at(1).running_seconds == 0
    assert state_at(47).running_seconds == 44
    assert state_at(51).running_seconds == 44
    assert state_at(53).running_seconds == 45
    assert sample_dynamic(47).engine_hours == sample_dynamic(51).engine_hours


def test_additional_nominal_sensors_and_thermal_continuity():
    assert sample_dynamic(0).oil_temperature_k == 293.15
    assert sample_dynamic(0).fuel_pressure_pa == 0
    assert sample_dynamic(0).engine_load_pct == 0
    assert sample_dynamic(3).fuel_pressure_pa == 150000
    assert sample_dynamic(5).engine_load_pct == 10
    assert sample_dynamic(25).engine_load_pct == 85
    assert sample_dynamic(25).fuel_pressure_pa == 300000
    assert sample_dynamic(46).oil_temperature_k > sample_dynamic(50).oil_temperature_k > 293.15
    for boundary in (2, 46, 50, 52, 96, 100):
        assert abs(sample_dynamic(boundary - .001).oil_temperature_k -
                   sample_dynamic(boundary + .001).oil_temperature_k) < .002
    assert sample_dynamic(10000).oil_temperature_k < 373.15
