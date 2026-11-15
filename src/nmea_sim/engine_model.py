"""Deterministic 50-second scripted engine state machine."""
import math
from dataclasses import dataclass
from enum import StrEnum
from .pgn_127488 import RapidUpdate
from .pgn_127489 import DynamicUpdate


class Phase(StrEnum):
    OFF = 'off'
    STARTING = 'starting'
    IDLE = 'idle'
    ACCELERATION = 'acceleration'
    CRUISE = 'cruise'
    DECELERATION = 'deceleration'


@dataclass(frozen=True)
class EngineState:
    phase: Phase
    rpm: float
    running_seconds: float


def _smooth(x: float) -> float:
    return x * x * (3 - 2 * x)


def state_at(elapsed: float) -> EngineState:
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('elapsed time must be finite and nonnegative')
    cycles, t = divmod(elapsed, 50)
    # This script counts running time from cranking until shutdown completes.
    running = cycles * 44 + max(0, min(t - 2, 44))
    if t < 2 or t >= 46:
        phase, rpm = Phase.OFF, 0.0
    elif t < 4:
        phase, rpm = Phase.STARTING, 750 * _smooth((t - 2) / 2)
    elif t < 9 or 39 <= t < 44:
        phase, rpm = Phase.IDLE, 750.0
    elif t < 19:
        phase, rpm = Phase.ACCELERATION, 750 + 3750 * _smooth((t - 9) / 10)
    elif t < 29:
        phase, rpm = Phase.CRUISE, 4500.0
    elif t < 39:
        phase, rpm = Phase.DECELERATION, 4500 - 3750 * _smooth((t - 29) / 10)
    else:
        phase, rpm = Phase.DECELERATION, 750 * (1 - _smooth((t - 44) / 2))
    return EngineState(phase, rpm, running)


def sample(elapsed: float) -> RapidUpdate:
    state = state_at(elapsed)
    load = max(0, (state.rpm - 750) / 3750)
    return RapidUpdate(0, state.rpm, None, round(-4 + 16 * load))


def oil_temperature(elapsed: float) -> float:
    """Exact first-order heating/cooling: 100°C running, 20°C off, tau 180s.

    The cycle runs at seconds 2–46. Closed-form cycle accumulation preserves
    heat at shutdown/restart without depending on sampling cadence.
    """
    cycles, t = divmod(elapsed, 50)
    decay = math.exp(-50 / 180)
    cycle_heat = 80 * (1 - math.exp(-44 / 180)) * math.exp(-4 / 180)
    excess = cycle_heat * (-math.expm1(-cycles * 50 / 180)) / (1 - decay)
    excess *= math.exp(-min(t, 2) / 180)
    if t > 2:
        excess = 80 + (excess - 80) * math.exp(-min(t - 2, 44) / 180)
    if t > 46:
        excess *= math.exp(-(t - 46) / 180)
    return 293.15 + excess


def sample_dynamic(elapsed: float, fault=None) -> DynamicUpdate:
    """Synthetic sensors consistent with off, cranking and running states."""
    state = state_at(elapsed)
    load = max(0, (state.rpm - 750) / 3750)
    idle_fraction = min(1, state.rpm / 750)
    charging = state.phase not in (Phase.OFF, Phase.STARTING) and state.rpm >= 750
    result = DynamicUpdate(
        instance=0,
        oil_pressure_pa=200000 * idle_fraction + 200000 * load,
        coolant_temperature_k=293.15 + 60 * (1 - math.exp(-state.running_seconds / 120)),
        alternator_voltage_v=14.2 if charging else 12.6,
        fuel_rate_lph=1.5 * idle_fraction + 33.5 * load,
        engine_hours=100 + state.running_seconds / 3600,
        oil_temperature_k=oil_temperature(elapsed),
        fuel_pressure_pa=300000 * idle_fraction,
        engine_load_pct=round(10 * idle_fraction + 75 * load),
        status1=0, status2=0,
    )
    return fault.apply(result, elapsed, state.rpm > 0) if fault is not None else result
