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
