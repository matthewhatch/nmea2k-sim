# M4 interoperability results and physical-readiness status

Date: 2026-11-13. Target hardware supplied by the user: **Waveshare 2-CH CAN HAT
(Isolated), Raspberry Pi 3**. These results cover Linux virtual CAN. Hardware
and Garmin acceptance remain unexecuted; no physical CAN interface was altered.

## Acceptance matrix

| Requirement | Status | Evidence / remaining condition |
| --- | --- | --- |
| Independent third-party decoding | PASS on vcan | CANboat 9.2.0 compared 79 discovery/conflict messages and 308 full-cycle engine messages |
| Actual captures and field-level results | PASS | Raw candump logs, independent JSON and hash-bearing validation reports under captures/ |
| Full engine cycle and unavailable fields | PASS on vcan | 51-second capture covers all six states, shutdown and stopped running-time behavior |
| Configuration-only channel selection | PASS in software tests | Shared CLI/env parser and unchanged SocketCAN transport; mocked physical metadata proves opt-in paths |
| Physical TX remains guarded | PASS in software tests | Missing opt-in blocks physical TX; unassigned 2046 is blocked even with opt-in; misleading interface names do not bypass checks |
| Target-specific bench procedure | DOCUMENTED | hardware-transition.md describes original 2-CH CAN HAT / Pi 3 checks and 250 kbit/s configuration |
| Pi driver, jumpers, wiring, voltage, termination | NOT RUN | Actual board/revision/OS, measurements and evidence required |
| Real can0 transmission and external ACK/reception | NOT RUN | Requires isolated powered bench, assigned identity and explicit operator approval |
| Garmin display discovery/engine gauges | NOT RUN | Exact display/firmware, supported fields and actual observations required |
| NMEA certification / full conformance | NOT CLAIMED | Public-reference implementations and vcan tests are not a certification audit |

Software preparation is complete; the physical portion of M4 must remain open
until the [bench acceptance record](bench-acceptance.md) is filled with actual
observations. A successful preflight report alone cannot close those gates.

## Independent tool and provenance

CANboat is an external reference/validation tool, **not a runtime dependency**.
The unmodified analyzer/converter were built from commit
`2a42e004e01094b25049dddf737277f33c324ff1`, reporting version 9.2.0.
The validator invokes those binaries separately from our decoder, compares
fields and records input/output and binary SHA-256 values. The supplied revision
field records the operator's source checkout; it is not a cryptographic
attestation of the binary's source. Binary hashes identify the exact local builds.

The M3 profile uses `analyzer -json`. The full-cycle profile uses `-json -nv`
so enumerated engine instance 1 is checked by its numeric value, not just its
display label. Our validator handles name/value lookup objects and explicitly
converts CANboat's standard units (bar, Celsius and wire seconds) to Pa, K and
hours. It rejects mismatches; tests deliberately corrupt independent output to
confirm this.

Both captures were decoded again during M4. Total independently compared:
**387 messages** (79 M3 + 308 full-cycle). No third-party binary is needed to run
the simulator or consumer, and normal offline tests replay the saved evidence.

## Full-cycle field results

`captures/m4-cycle.log`: 464 real extended classic CAN frames on vcan0, source
230, engine instance 1. Duration: approximately 51 seconds. They reconstruct
256 rapid messages and 52 dynamic fast-packet messages. Capture SHA-256:
`914505243461061a8cd0b25a93c11cffde1df9ad8e15d12bc8c844be06045c09`.

| Field | Independently matched range / result |
| --- | --- |
| RPM | 0 to 4500, 0.25 RPM resolution |
| Trim | -4 to 12 percent |
| Oil pressure | 0 to 400000 Pa |
| Coolant temperature | 293.15 to 311.57 K (20.00 to 38.42 Celsius) |
| Alternator voltage | 12.6 to 14.2 V |
| Fuel rate | 0 to 35.0 L/h |
| Engine hours | 100 to 100.012222… (wire seconds 360000 to 360044) |
| Off/shutdown | RPM, fuel flow and oil pressure return to zero; engine hours stop increasing |
| Unsupported measurements | Boost, oil temperature, coolant/fuel pressure, load and torque unavailable |
| Status words | Nominal zero flags; no fault scenario was injected |

Capture replay checks all six state categories, 51-second duration, 5 Hz / 1 Hz
cadence and stopped running time. Interval tolerances are ±50 ms for rapid and
±100 ms for dynamic in this quiet virtual capture; total duration tolerance is
±0.5 s. This is timestamp evidence on Linux, not a hard real-time guarantee.

## Reproduction

After package installation and virtual-CAN setup, reserve source 230:

```sh
env/bin/python scripts/capture_cycle.py --output /tmp/m4-cycle.log
```

The script verifies kernel-vcan, invokes a separate bounded simulator and records
candump output. It never configures an interface and cannot use the default test
identity on physical CAN. Capturing takes roughly 52 seconds including startup.
A source collision, simulator error or incomplete capture causes explicit failure.

Use the independently built tools (build commands in captures/README.md):

```sh
env/bin/python scripts/validate_canboat.py \
  --profile cycle --capture docs/captures/m4-cycle.log \
  --analyzer /tmp/nmea-canboat-m3/rel/linux-x86_64/analyzer \
  --converter /tmp/nmea-canboat-m3/rel/linux-x86_64/candump2analyzer \
  --canboat-revision 2a42e004e01094b25049dddf737277f33c324ff1 \
  --output /tmp/m4-cycle.canboat.jsonl
```

Substitute your CANboat binary paths/platform directory. Reports record version,
message counts, field ranges and SHA-256 values. Do not overwrite committed
fixtures without reviewing the new capture and passing its replay checks.

Read-only host checks and offline regression:

```sh
env/bin/python -m nmea_sim.preflight --channel vcan0
env/bin/python -m pytest -q tests/test_cycle_capture.py tests/test_preflight.py tests/test_transport.py
```

The actual vcan0 preflight passed interface/type/UP checks and explicitly did
not authorize physical transmission. See hardware-transition.md for read-only
can0 inspection and the separately gated bench commands.


## Test results

Final M4 suite: **368 passed in 12.57s**, with real vcan0 access and no skips.
Restricted-sandbox suite: **364 passed, 4 skipped in 0.28s** because the live
vcan interface is unavailable in that namespace. Capture replay, independent
field comparisons, preflight and guard tests all run offline. Physical paths
were exercised only through explicitly synthetic/mocked interface metadata.
The actual read-only vcan0 preflight passed. No can0 configuration or TX occurred.
