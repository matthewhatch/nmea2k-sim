import pytest
from nmea_sim import simulator
from nmea_sim.can_id import extract


def test_independent_configurable_rates(monkeypatch):
    clock = [0.0]
    frames = []
    class Bus:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def recv(self, timeout):
            clock[0] += timeout
            return None
        def send(self, message, timeout):
            frames.append((clock[0], message))
    monkeypatch.setattr(simulator, 'open_bus', lambda *a, **kw: Bus())
    monkeypatch.setattr(simulator.time, 'monotonic', lambda: clock[0])
    def sleep(duration):
        clock[0] += duration
    monkeypatch.setattr(simulator.time, 'sleep', sleep)
    assert simulator.main(['--unique-number', '1', '--channel', 'vcan0', '--rapid-hz', '10', '--dynamic-hz', '2', '--count', '11']) == 0
    rapid = [(t, m) for t, m in frames if extract(m.arbitration_id).pgn == 127488]
    dynamic = [(t, m) for t, m in frames if extract(m.arbitration_id).pgn == 127489]
    assert [t for t, _ in rapid] == pytest.approx([.25 + i / 10 for i in range(11)])
    assert len(dynamic) == 12
    assert [t for t, m in dynamic if m.data[0] & 31 == 0] == pytest.approx([.25, .75, 1.25])
    assert all(m.is_extended_id and len(m.data) == 8 for _, m in frames)


def test_scheduled_fault_reaches_can_and_recovers(monkeypatch, caplog):
    import logging
    from nmea_sim.receiver import Decoder
    from nmea_sim.pgn_127489 import DynamicUpdate, Status1
    clock, records = [0.0], []
    decoder = Decoder()
    class Bus:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def recv(self, timeout):
            clock[0] += timeout
        def send(self, message, timeout):
            state = decoder.receive(message)
            if isinstance(state, DynamicUpdate):
                records.append((clock[0] - .25, state))
    monkeypatch.setattr(simulator, 'open_bus', lambda *a, **kw: Bus())
    monkeypatch.setattr(simulator.time, 'monotonic', lambda: clock[0])
    with caplog.at_level(logging.INFO):
        assert simulator.main(['--unique-number', '1', '--count', '41', '--fault',
                               'low-fuel-pressure', '--fault-start', '4', '--fault-duration', '2']) == 0
    before = [s for t, s in records if 3 <= t < 4]
    active = [s for t, s in records if 4 <= t < 6]
    after = [s for t, s in records if t >= 6]
    assert before and active and after
    assert all(not s.status1 for s in before + after)
    assert all(s.status1 & Status1.LOW_FUEL_PRESSURE and s.fuel_pressure_pa == 60000 for s in active)
    assert 'fault_active' in caplog.text and 'fault_recovery' in caplog.text
