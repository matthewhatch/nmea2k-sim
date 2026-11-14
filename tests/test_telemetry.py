from dataclasses import replace
import pytest
from nmea_sim.telemetry import TelemetryStore
from nmea_sim.pgn_127488 import RapidUpdate
from nmea_sim.pgn_127489 import DynamicUpdate, Status1, Status2
from nmea_sim.device_protocol import Name


@pytest.fixture
def state():
    now = [0.0]
    store = TelemetryStore(stale_after=3, clock=lambda: now[0])
    return store, now


def test_values_and_units_from_decoded_telemetry(state):
    store, _ = state
    store.accept(35, RapidUpdate(0, 3000, None, -4))
    store.accept(35, DynamicUpdate(coolant_temperature_k=353.15, alternator_voltage_v=14.2,
                                 oil_pressure_pa=250000, fuel_rate_lph=12.3, engine_hours=100))
    view = store.view('35:0')
    assert view['status'] == 'fresh'
    assert view['rpm'] == 3000 and view['running'] == 'Running'
    assert view['temperature_c'] == pytest.approx(80)
    assert view['oil_pressure_bar'] == 2.5
    assert view['engine_hours'] == 100 and view['trim'] == -4


def test_missing_is_not_zero(state):
    store, _ = state
    view = store.view(None)
    assert view['status'] == 'no_data' and view['rpm'] is None
    store.accept(35, RapidUpdate(0, 0, None, 0))
    store.accept(35, DynamicUpdate())
    view = store.view('35:0')
    assert view['rpm'] == 0 and view['running'] == 'Stopped' and view['trim'] == 0
    assert view['temperature_c'] is None and view['voltage_v'] is None
    store.accept(35, RapidUpdate(0, None, None, None))
    assert store.view('35:0')['running'] == 'Unknown'


def test_per_pgn_staleness_no_false_refresh(state):
    store, now = state
    store.accept(35, RapidUpdate(0, 750, None, 0))
    store.accept(35, DynamicUpdate(alternator_voltage_v=14.2, status1=Status1.LOW_SYSTEM_VOLTAGE))
    now[0] = 3
    store.accept(35, RapidUpdate(0, 800, None, 1))
    view = store.view('35:0')
    assert view['status'] == 'partial' and view['rpm'] == 800
    assert view['voltage_v'] is None and view['low_voltage'] is None
    assert not view['warning_known']
    now[0] = 6
    view = store.view('35:0')
    assert view['status'] == 'stale' and view['rpm'] is None and view['running'] == 'Unknown'


def test_disconnection_hides_values_immediately(state):
    store, _ = state
    store.accept(35, RapidUpdate(0, 3000, None, 0))
    view = store.view('35:0', connected=False)
    assert view['status'] == 'disconnected' and view['rpm'] is None


def test_multiple_sources_and_instances_do_not_merge(state):
    store, _ = state
    store.accept(35, RapidUpdate(0, 750, None, -4))
    store.accept(35, RapidUpdate(1, 1500, None, 4))
    store.accept(36, DynamicUpdate(instance=0, alternator_voltage_v=13.8))
    assert len(store.choices()) == 3
    assert store.view('35:0')['rpm'] == 750
    assert store.view('35:1')['rpm'] == 1500
    assert store.view('36:0')['rpm'] is None
    assert store.view('35:0')['voltage_v'] is None
    assert store.view('36:0')['voltage_v'] == 13.8


def test_only_reported_bits_create_alarms(state):
    store, _ = state
    store.accept(35, DynamicUpdate(coolant_temperature_k=400, oil_pressure_pa=0, alternator_voltage_v=0))
    view = store.view('35:0')
    assert view['high_temperature'] is False and view['low_oil_pressure'] is False and view['low_voltage'] is False
    store.accept(35, DynamicUpdate(status1=Status1.OVER_TEMPERATURE | Status1.LOW_OIL_PRESSURE |
                                 Status1.LOW_SYSTEM_VOLTAGE, status2=Status2.WARNING_LEVEL_1))
    view = store.view('35:0')
    assert view['high_temperature'] and view['low_oil_pressure'] and view['low_voltage']
    assert 'WARNING_LEVEL_1' in view['warnings']


def test_known_source_replacement_clears_old_sensors(state):
    store, _ = state
    store.accept(35, Name(1, 2046))
    store.accept(35, RapidUpdate(0, 3000, None, -4))
    store.accept(35, Name(2, 2046))
    assert store.choices() == []
    store.accept(35, DynamicUpdate(alternator_voltage_v=14.2))
    assert store.view('35:0')['rpm'] is None


def test_capacity_and_unknown_instances(state):
    store = TelemetryStore(max_engines=2)
    assert store.accept(35, RapidUpdate(None, 750, None, -4)) is None
    assert store.accept(254, RapidUpdate(0, 750, None, -4)) is None
    for source in (35, 36, 37):
        store.accept(source, RapidUpdate(0, 750, None, -4))
    assert len(store.choices()) == 2
