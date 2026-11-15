# Milestone M7 — Additional Engine Metrics and Fault Scenarios

Implementation: delivered. Usage and model assumptions: [metrics and faults](../FAULTS.md).
Evidence: [real vcan capture](../captures/m7-fault.log) and
[decoded raw-field summary](../captures/m7-fault.json). Local and two-client
socketcand integration checks cover the new metrics and fault activation/recovery.
Validation: 442 tests passed with real vcan0 and socketcand, with no skips.

## Objective

Extend the simulator and native dashboard with oil temperature, fuel pressure,
engine load, and selectable fault scenarios. Continue using native NMEA 2000
traffic through local SocketCAN or the M6 socketcand gateway.

The simulated engine remains a generic outboard inspired by the Yamaha F115.
Values are synthetic model outputs, not verified F115 sensor readings or Yamaha
proprietary protocol emulation.

## Current State

- PGN 127489 already encodes and decodes oil temperature, fuel pressure, engine
  load, and engine status bitfields.
- The engine model currently leaves those three measurements unavailable and
  sends clear status words.
- The dashboard displays RPM, coolant temperature, alternator voltage, oil
  pressure, fuel rate, engine hours, trim, and received warning flags.
- The telemetry view does not yet expose the three additional measurements.

## M7.1 — Model Additional Measurements

| Measurement | Existing protocol field | Dashboard unit |
| --- | --- | --- |
| Oil temperature | PGN 127489 oil temperature | °C |
| Fuel pressure | PGN 127489 fuel pressure | bar |
| Engine load | PGN 127489 engine load | % |

Requirements:

- Define documented nominal ranges and behavior for off, starting, idle,
  acceleration, cruise, and deceleration.
- Model oil temperature with warm-up and cooling inertia rather than an
  instantaneous RPM lookup.
- Model fuel pressure with documented engine-off and startup behavior.
- Model load independently of RPM where possible; define its meaning and limits.
- Keep model units explicit: kelvin, pascals, and percent at the encoder boundary.
- Preserve existing field resolution, reserved bytes, and unavailable sentinels.
- Keep unsupported measurements unavailable rather than assigning placeholders.
- Make output deterministic for a given scenario and elapsed simulation time.

## M7.2 — Dashboard Instruments

- Add oil temperature, fuel pressure, and engine load instruments or metric tiles.
- Expose values through the existing decoded telemetry store and Qt backend.
- Derive every displayed measurement from received CAN traffic.
- Apply existing dynamic-message freshness rules to the new measurements.
- Show unavailable, stale, and disconnected values consistently with existing tiles.
- Preserve usability at the dashboard's supported window sizes.
- Keep warning indicators tied to received status bits; do not invent fault
  flags from dashboard measurement thresholds.

## M7.3 — Selectable Fault Scenarios

Add named simulator scenarios selected at startup. Proposed interface, to be
finalized during implementation:

```sh
env/bin/python -m nmea_sim.simulator --channel vcan0 --fault none
env/bin/python -m nmea_sim.simulator --channel vcan0 \
  --fault low-fuel-pressure --fault-start 20 --fault-duration 10
```

Times are seconds of simulation time from scenario start. Default to no fault.
Initial scope is one active fault at a time; overlapping faults and live remote
control are deferred. Reject unknown names, non-finite or negative times, and
non-positive durations before opening the bus. Define behavior when an activation
extends past a bounded run or the existing engine cycle restarts.

| Scenario | Measurement behavior | Reported status |
| --- | --- | --- |
| Overheating | Coolant temperature rises with a defined recovery curve | OVER_TEMPERATURE |
| Low oil pressure | Oil pressure drops while the engine runs | LOW_OIL_PRESSURE |
| Low fuel pressure | Fuel pressure drops; document any load/RPM response | LOW_FUEL_PRESSURE |
| Charging failure | Alternator voltage declines toward battery voltage | CHARGE_INDICATOR and/or LOW_SYSTEM_VOLTAGE according to documented stages |

Requirements:

- Define activation, progression, recovery, and status clearing for each fault.
- Keep nominal behavior unchanged outside the fault interval except for modeled
  recovery effects, such as retained heat.
- Explicitly define behavior when the engine is stopped or starting.
- Use existing PGN 127489 status bits and transport; no custom fault telemetry.
- Preserve unrelated status bits when applying or clearing a fault.
- Log scenario activation and recovery locally for diagnosis.
- Display the received warning and affected measurement on both local and remote
  dashboards. Scenario selection belongs to simulator configuration; the
  dashboard remains receive-only.

## M7.4 — Validation

- Verify new fields through encode/decode and fast-packet reassembly, including
  units, quantization, unavailable values, and range boundaries.
- Test deterministic nominal behavior and each fault's activation/recovery edges.
- Verify unrelated measurements and status bits remain correct during faults.
- Test dashboard conversion, freshness, warning transitions, and unavailable data.
- Run a bounded vcan0 capture with an independent receiver and compare decoded
  measurements and status bits against the scenario timeline.
- Exercise socketcand reception to confirm the same values reach a remote dashboard.
- Run existing protocol, simulator, telemetry, and dashboard regression checks.

## Deliverables and Acceptance Criteria

- [x] All three new measurements are generated, transmitted, decoded, and displayed.
- [x] Nominal behavior and synthetic model assumptions are documented.
- [x] Each named fault is selectable and has deterministic timing and recovery.
- [x] Warning flags agree with the documented scenario behavior.
- [x] Missing or stale data never appears as a healthy zero measurement.
- [x] Local and remote dashboards show equivalent decoded telemetry.
- [x] Automated checks and a reproducible capture demonstrate the behavior.
- [x] Existing default simulation and physical-transmission safeguards remain intact.
- [x] README and dashboard instructions include runnable scenario examples.

## Out of Scope

Additional PGNs, proprietary Yamaha messages, verified F115 calibration, vessel
navigation, fuel tank level, live dashboard control, and physical-network
acceptance testing. Trip orchestration follows in [M8](MILESTONE8.md).
