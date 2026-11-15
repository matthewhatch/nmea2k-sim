# Milestone M8 — Realistic Trip Simulation with Fault Events

## Objective

Simulate a coherent outboard trip: start at a marina berth, warm up, leave the
marina at low speed, accelerate into open water, cruise, and return to berth.
Introduce scheduled fault scenarios during the trip using the metrics and fault
model delivered by [M7](MILESTONE7.md).

Realism means continuous, internally consistent synthetic engine behavior with
documented assumptions. It does not imply calibrated Yamaha F115 performance,
navigation accuracy, or a certified vessel model.

## Dependencies

- M7 additional metrics, fault models, dashboard instruments, and warning display.
- Existing ISO device behavior, PGN 127488/127489 transport, and SocketCAN support.
- M6 socketcand transport for monitoring a Pi from a remote dashboard.

## M8.1 — Trip Timeline

Provide a named trip profile with a documented default duration and configurable
phase durations. The following order defines the initial profile; final timing
and operating ranges must be documented during implementation.

| Phase | Engine behavior |
| --- | --- |
| Berthed, engine off | Zero RPM, no charging, retained thermal state |
| Starting and warm-up | Startup transient, idle, gradual warming |
| Leaving berth | Low-load maneuvering with gentle RPM changes |
| Marina transit | Sustained low RPM and modest load with small variations |
| Entering open water | Gradual acceleration, increasing load and fuel consumption |
| Open-water cruise | Sustained running with bounded throttle/load changes |
| Return and approach | Deceleration followed by low-load marina transit |
| Docking and shutdown | Maneuvering, idle, stop, and initial cooling |

Requirements:

- Use one simulation clock for phases, measurements, and fault events.
- Preserve continuous oil/coolant temperature and cumulative engine hours across
  phase boundaries. Do not reset state when cruise begins or the engine stops.
- Correlate RPM, load, oil pressure, fuel pressure, charging voltage, fuel rate,
  temperature, and trim through documented model rules.
- Apply bounded ramps and thermal lag; reserve abrupt transitions for explicitly
  modeled events such as shutdown or a sudden pressure fault.
- Support repeatable variation with a configurable seed; avoid frame-by-frame
  random jitter unrelated to engine dynamics.
- Preserve the existing short engine cycle as the default compatibility profile.
- Run a trip once by default and define orderly completion and final engine state.
- Keep marina/open-water location as scenario context; no GPS, speed, or position
  PGNs are required for this milestone.

## M8.2 — Scheduled Fault Events

Reuse M7 faults rather than implementing a second fault engine. Supply a clean
trip and a demonstration trip with scheduled events, for example:

1. Charging failure during marina transit, followed by recovery.
2. Low fuel pressure during open-water cruise, followed by a documented response.
3. Overheating during sustained load, followed by reduced load and gradual cooling.

Requirements:

- Specify events relative to a named phase and offset, with explicit durations.
- Validate unknown phases/faults, invalid offsets, out-of-phase events, and overlaps
  before transmission. Initial scope uses non-overlapping faults.
- Document event precedence over nominal trip measurements and control inputs.
- If the scenario models an operator reducing throttle or stopping the engine,
  schedule that action explicitly and distinguish it from the fault itself.
- Set POWER_REDUCTION only when the scenario models an engine-reported reduction;
  ordinary operator throttle reduction does not imply that status bit.
- Preserve residual heat and other recovery state after fault flags clear.
- Ensure the clean trip has no injected faults.

## M8.3 — Configuration and Observability

Proposed commands, to be finalized during implementation:

```sh
env/bin/python -m nmea_sim.simulator --channel vcan0 \
  --profile marina-trip --seed 115

env/bin/python -m nmea_sim.simulator --channel vcan0 \
  --profile marina-trip-faults --seed 115
```

- Document profile selection, durations, seed, completion, and interaction with
  existing bounded-run options and M7 fault-selection options.
- Log phase entry, fault activation, recovery, and trip completion with simulation
  timestamps. Publish a matching timeline for reproducing demonstrations.
- Keep phase names and scheduling metadata local to simulator diagnostics; the
  dashboard continues to show measurements and status decoded from CAN frames.
- Preserve PGN transmission cadence regardless of scenario phase.
- Use accelerated model time for automated tests without flooding the CAN bus;
  define any user-facing speed multiplier separately before implementing it.

## M8.4 — Validation

- Verify deterministic output for identical profiles, seeds, and elapsed times.
- Test every phase boundary, engine start/stop, trip completion, and invalid profile.
- Verify thermal continuity, engine-hour accumulation only while running, bounded
  measurements, and fault recovery across phase boundaries.
- Check scheduled events and affected status bits against the expected timeline.
- Capture a complete trip on vcan0 and decode it independently, checking phase
  trends, PGN cadence, payload validity, and fast-packet reassembly.
- Verify a remote dashboard displays the progression and fault/recovery events
  through socketcand, including recovery after a gateway interruption.
- Run existing short-cycle and M7 regression checks.

## Deliverables and Acceptance Criteria

- [ ] A complete clean marina-to-open-water-and-return trip runs to completion.
- [ ] A fault demonstration trip includes documented, reproducible events.
- [ ] Measurements vary coherently with phase, load, warm-up, and recovery.
- [ ] Phase transitions preserve state and introduce no unexplained discontinuities.
- [ ] Dashboard warning indicators follow received status flags during each event.
- [ ] Profiles and timelines are documented with runnable Pi/gateway/client commands.
- [ ] Automated checks and a decoded trip capture substantiate the behavior.
- [ ] Existing default cycle, device identity behavior, and TX safeguards remain intact.

## Out of Scope

GPS routes or maps, vessel hydrodynamics, weather/wave simulation, tank-level or
navigation PGNs, interactive helm controls, remote dashboard commands, overlapping
fault composition, and physical engine or operational boat-network testing.
