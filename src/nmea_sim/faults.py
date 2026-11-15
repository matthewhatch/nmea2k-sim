"""One deterministic, non-repeating fault interval on the model clock."""
import math
from dataclasses import dataclass, replace
from .pgn_127489 import DynamicUpdate, Status1

FAULT_NAMES = ('none', 'overheating', 'low-oil-pressure', 'low-fuel-pressure', 'charging-failure')


@dataclass(frozen=True)
class FaultScenario:
    name: str = 'none'
    start: float = 20.0
    duration: float = 10.0

    def __post_init__(self):
        if self.name not in FAULT_NAMES:
            raise ValueError('unknown fault scenario')
        if not math.isfinite(self.start) or self.start < 0:
            raise ValueError('fault start must be finite and nonnegative')
        if not math.isfinite(self.duration) or self.duration <= 0:
            raise ValueError('fault duration must be finite and positive')
        if not math.isfinite(self.start + self.duration):
            raise ValueError('fault end must be finite')

    def stage(self, elapsed: float) -> str:
        if self.name == 'none':
            return 'disabled'
        if elapsed < self.start:
            return 'pending'
        return 'active' if elapsed < self.start + self.duration else 'recovery'

    def apply(self, state: DynamicUpdate, elapsed: float, running: bool) -> DynamicUpdate:
        """Pressure/electrical faults clear immediately; excess coolant heat decays.

        No RPM/load response is implied. Fault bits represent the scheduled
        diagnostic condition, not dashboard measurement thresholds.
        """
        stage = self.stage(elapsed)
        if stage in ('disabled', 'pending'):
            return state
        active = stage == 'active'
        changes = {}
        bits = 0
        if self.name == 'overheating':
            # Integrate only time with a rotating engine during the interval.
            from .engine_model import state_at
            end = min(elapsed, self.start + self.duration)
            heating = state_at(end).running_seconds - state_at(self.start).running_seconds
            excess = 80 * (1 - math.exp(-heating / 5))
            if not active:
                excess *= math.exp(-(elapsed - end) / 30)
            if state.coolant_temperature_k is not None:
                changes['coolant_temperature_k'] = state.coolant_temperature_k + excess
            if active and running:
                bits |= Status1.OVER_TEMPERATURE
        elif active and running:
            if self.name == 'low-oil-pressure':
                if state.oil_pressure_pa is not None:
                    changes['oil_pressure_pa'] = state.oil_pressure_pa * .1
                bits |= Status1.LOW_OIL_PRESSURE
            elif self.name == 'low-fuel-pressure':
                if state.fuel_pressure_pa is not None:
                    changes['fuel_pressure_pa'] = state.fuel_pressure_pa * .2
                bits |= Status1.LOW_FUEL_PRESSURE
            elif self.name == 'charging-failure':
                age = elapsed - self.start
                voltage = 12.6 - .8 * (1 - math.exp(-age / 5))
                changes['alternator_voltage_v'] = voltage
                bits |= Status1.CHARGE_INDICATOR
                if voltage < 12:
                    bits |= Status1.LOW_SYSTEM_VOLTAGE
        return replace(state, status1=state.status1 | bits, **changes)
