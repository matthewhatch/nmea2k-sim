"""GUI-independent engine state. Values come solely from decoded received PGNs."""
import math
import time
from dataclasses import dataclass
from typing import Callable
from .pgn_127488 import RapidUpdate
from .pgn_127489 import DynamicUpdate, Status1, active_status
from .device_protocol import Name


@dataclass
class _Engine:
    source: int
    instance: int
    rapid: RapidUpdate | None = None
    dynamic: DynamicUpdate | None = None
    rapid_seen: float | None = None
    dynamic_seen: float | None = None


class TelemetryStore:
    def __init__(self, stale_after: float = 3, clock: Callable[[], float] = time.monotonic,
                 max_engines: int = 128):
        if not math.isfinite(stale_after) or stale_after <= 0 or max_engines < 1:
            raise ValueError('positive finite timeout and capacity required')
        self.stale_after, self.clock, self.max_engines = stale_after, clock, max_engines
        self.engines: dict[str, _Engine] = {}
        self.names: dict[int, int] = {}

    def accept(self, source: int, state) -> str | None:
        if not 0 <= source <= 251:
            return None
        if isinstance(state, Name):
            previous = self.names.get(source)
            if previous != state.value:
                for key in [key for key, engine in self.engines.items() if engine.source == source]:
                    del self.engines[key]  # never combine sensors across a known device replacement
            self.names[source] = state.value
            return None
        if not isinstance(state, (RapidUpdate, DynamicUpdate)) or state.instance is None or source > 251:
            return None
        key = f'{source}:{state.instance}'
        if key not in self.engines:
            if len(self.engines) >= self.max_engines:
                oldest = min(self.engines, key=lambda k: max(self.engines[k].rapid_seen or -1,
                                                            self.engines[k].dynamic_seen or -1))
                del self.engines[oldest]
            self.engines[key] = _Engine(source, state.instance)
        engine = self.engines[key]
        if isinstance(state, RapidUpdate):
            engine.rapid, engine.rapid_seen = state, self.clock()
        else:
            engine.dynamic, engine.dynamic_seen = state, self.clock()
        return key

    def choices(self) -> list[dict]:
        return [{'key': key, 'label': f'Engine {e.instance}  ·  Source {e.source}'}
                for key, e in sorted(self.engines.items(), key=lambda item: (item[1].instance, item[1].source))]

    def view(self, key: str | None, connected: bool = True) -> dict:
        engine = self.engines.get(key)
        now = self.clock()
        rapid_age = None if engine is None or engine.rapid_seen is None else max(0, now - engine.rapid_seen)
        dynamic_age = None if engine is None or engine.dynamic_seen is None else max(0, now - engine.dynamic_seen)
        rapid_fresh = connected and rapid_age is not None and rapid_age < self.stale_after
        dynamic_fresh = connected and dynamic_age is not None and dynamic_age < self.stale_after
        rapid = engine.rapid if engine and rapid_fresh else None
        dynamic = engine.dynamic if engine and dynamic_fresh else None
        status = ('disconnected' if not connected else 'no_data' if engine is None else
                  'fresh' if rapid_fresh and dynamic_fresh else 'partial' if rapid_fresh or dynamic_fresh else 'stale')
        rpm = rapid.rpm if rapid else None
        running = 'Unknown' if rpm is None else 'Running' if rpm > 0 else 'Stopped'
        warnings = active_status(dynamic) if dynamic else []
        # These are protocol-reported bits, never thresholds applied to measurements.
        flags = dynamic.status1 if dynamic else None
        return {'key': key or '', 'source': engine.source if engine else None,
                'instance': engine.instance if engine else None, 'status': status,
                'running': running, 'rapid_fresh': rapid_fresh, 'dynamic_fresh': dynamic_fresh,
                'rapid_age': rapid_age, 'dynamic_age': dynamic_age,
                'rpm': rpm, 'trim': rapid.trim if rapid else None,
                'temperature_c': dynamic.coolant_temperature_k - 273.15
                    if dynamic and dynamic.coolant_temperature_k is not None else None,
                'voltage_v': dynamic.alternator_voltage_v if dynamic else None,
                'oil_pressure_bar': dynamic.oil_pressure_pa / 100000
                    if dynamic and dynamic.oil_pressure_pa is not None else None,
                'fuel_rate_lph': dynamic.fuel_rate_lph if dynamic else None,
                'engine_hours': dynamic.engine_hours if dynamic else None,
                'high_temperature': None if flags is None else bool(flags & Status1.OVER_TEMPERATURE),
                'low_oil_pressure': None if flags is None else bool(flags & Status1.LOW_OIL_PRESSURE),
                'low_voltage': None if flags is None else bool(flags & Status1.LOW_SYSTEM_VOLTAGE),
                'warnings': warnings, 'warning_known': dynamic_fresh,
                'status1': dynamic.status1 if dynamic else None,
                'status2': dynamic.status2 if dynamic else None}
