# Additional engine metrics and fault scenarios (M7)

Install the simulator using `env/bin/python -m pip install -e .` on the Pi.
Use `.[dashboard]` on a compatible dashboard host. No new dependencies are needed.

## Nominal measurements

PGN 127489 now carries these synthetic measurements:

| Measurement | Model | Dashboard unit |
| --- | --- | --- |
| Oil temperature | Starts at 20°C; approaches 100°C while cranking/running and 20°C while off, with a 180-second time constant | °C |
| Fuel pressure | 0 bar off, proportional to startup RPM up to 3 bar at idle, then constant | bar |
| Engine load | 0% off, 10% at idle, rising to 85% at 4500 RPM | % |

Oil temperature retains heat across the 50-second cycle and cools at shutdown.
The closed-form model is independent of sampling cadence. Load is an approximate
RPM-derived demand, not measured torque or an independent propeller model.
Torque and coolant pressure remain unavailable. These assumptions are not
calibrated F115 values or a claim of actual F115 sensor availability.

## Select a fault

```sh
env/bin/python -m nmea_sim.simulator --channel vcan0 \
  --fault low-fuel-pressure --fault-start 20 --fault-duration 10
```

Defaults: `--fault none`, `--fault-start 20`, `--fault-duration 10`. Start must be
finite and nonnegative; duration must be finite and positive. Invalid options
fail before opening the bus.

Times are model seconds starting when the simulator first owns its address.
The interval includes its start and excludes its end, and runs once per process,
not once per engine cycle. Address reacquisition preserves the model clock.
A bounded `--count` run may end before an event or recovery; it is not extended.
Logs report `fault_active` and `fault_recovery` when the loop observes transitions.

| Fault | Active behavior | Recovery |
| --- | --- | --- |
| `overheating` | Excess coolant heat approaches +80°C with a 5-second time constant based on running time within the interval; OVER_TEMPERATURE | Flag clears at interval end; excess heat decays with a 30-second time constant |
| `low-oil-pressure` | 10% of nominal oil pressure; LOW_OIL_PRESSURE | Immediate nominal pressure and flag clearing |
| `low-fuel-pressure` | 20% of nominal fuel pressure; LOW_FUEL_PRESSURE | Immediate nominal pressure and flag clearing |
| `charging-failure` | Voltage starts at 12.6 V and approaches 11.8 V with a 5-second time constant; CHARGE_INDICATOR plus LOW_SYSTEM_VOLTAGE below 12 V | Immediate nominal voltage and flag clearing |

Effects and new warning bits are suppressed at zero RPM. Pressure/electrical
faults apply during cranking once RPM is positive. Overheating accumulates only
during the model's running interval, including cranking; retained heat remains
visible while stopped. Charging progression uses elapsed fault time, including
stopped time. No fault changes RPM, fuel rate, or load. No automatic throttle
response is modeled. Unrelated status bits are preserved.

The overheating bit represents the injected diagnostic interval, not a numeric
threshold: it can clear while residual heat remains. The dashboard displays
received status bits rather than inferring warnings from measurements.

## Dashboard and capture

The new metrics appear in a two-row grid and follow dynamic-PGN freshness rules.
Unavailable, stale, and disconnected values show `--`. The existing warning list
shows the active reported flags. The dashboard remains receive-only.
At compact window heights the two main instruments use numeric readouts to keep
their values and labels readable; larger layouts retain the analog dials.

```sh
env/bin/python -m nmea_sim.dashboard --channel vcan0
# Or connect to the Pi's socketcand gateway:
env/bin/python -m nmea_sim.dashboard --transport socketcand \
  --host 192.168.1.181 --port 29536 --channel vcan0
```

See [gateway setup](ETHERNET.md). Existing device identity and physical-TX
restrictions remain in effect.

With vcan0 configured and source/unique number 238 unused, capture an event:

```sh
env/bin/python scripts/capture_fault.py
```

This records about nine seconds of real CAN traffic and verifies a pressure fault
at seconds 4–6, its recovery, and the new fields using independent raw payload
offsets. Output defaults to `docs/captures/m7-fault.log` and a JSON summary.
