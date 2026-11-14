# NMEA 2000 engine simulator

A generic single-outboard simulator and separate, receive-only console consumer.
Telemetry travels exclusively as NMEA 2000 frames on Linux SocketCAN. No HTTP,
WebSocket, MQTT, Signal K service or custom network transport is included or
planned. `vcan0` is local to a host/network namespace, not a LAN service.
This project does not impersonate Yamaha or claim NMEA certification.

M0–M3 are implemented and tested on virtual CAN, including discovery and
address conflict handling. The default identity is explicitly unassigned and
restricted to virtual CAN. M4 virtual validation and bench preparation are complete;
physical acceptance is pending; this is not a
certified or fully conformant physical NMEA 2000 node.

## Install and set up virtual CAN

Requires Linux, Python 3.11+, python-can, iproute2, kmod and can-utils. Package
installation needs access to the package index; operation and tests work offline
once installed.

```sh
python3 -m venv env
env/bin/python -m pip install -e '.[test]'
sudo apt install can-utils iproute2 kmod
sudo scripts/setup_vcan.sh
```

The idempotent setup script creates/raises only `vcan0` and refuses to alter an
existing interface of a different type. It needs host network administration
permission. Neither application creates or configures any interface.

## Run in separate terminals

```sh
# Terminal 1: CAN-only consumer, prints console diagnostic JSON lines
env/bin/python -m nmea_sim.consumer --channel vcan0

# Terminal 2: simulator
env/bin/python -m nmea_sim.simulator --channel vcan0

# Terminal 3: independent raw-frame inspection
candump -L vcan0
```

`nmea_sim.receiver` and the `nmea-receiver` console command remain compatibility
aliases; `nmea-consumer` is the new console command after package installation.
Ctrl-C cleanly stops either process. The consumer needs no transmit opt-in,
imports no model state, and derives every engine value from received CAN frames.
Its JSON is local diagnostic output, not a telemetry transport. It does not
infer that arbitrary received traffic is simulated.

If preferred source 35 is available, engine extended identifiers are `09F20023` (127488) and `09F20123` (127489),
priority 2, source 35. Initial rapid payload: `00 00 00 FF FF FC FF FF` (off,
instance zero, unavailable boost, trim -4). Dynamic updates use four fast-packet
frames per message. Consumer rows contain PGN, source, final-frame timestamp,
and decoded fields. Unavailable measurements are `null`; incomplete dynamic
packets never produce a telemetry row.

For a bounded engine demo, leave the consumer running and start:

```sh
env/bin/python -m nmea_sim.simulator --count 41
```

After address acquisition this emits 41 rapid and 9 dynamic messages over eight
seconds, plus address claims and heartbeats. Stop the consumer with Ctrl-C.
Simulator `--count` counts rapid messages; consumer `--count` counts every
complete diagnostic message, including discovery/requests/heartbeat. A bounded
consumer exits with status 1 on inactivity; an unbounded consumer keeps listening.
Malformed payloads are logged and ignored.

## Configuration

CLI overrides environment, which overrides defaults. `.env.example` is a
template, not automatically loaded. Both entrypoints share the parser.

| Setting | Default | Environment | CLI |
| --- | --- | --- | --- |
| CAN channel | vcan0 | NMEA_CAN_CHANNEL | --channel |
| Preferred source address | 35 | NMEA_SOURCE_ADDRESS | --source-address |
| Rapid rate | 5 Hz | NMEA_RAPID_HZ | --rapid-hz |
| Dynamic rate | 1 Hz | NMEA_DYNAMIC_HZ | --dynamic-hz |
| Physical TX opt-in | false | none | --allow-physical-tx |
| Manufacturer code | 2046 (vcan test only) | NMEA_MANUFACTURER_CODE | --manufacturer-code |
| Unique number | stable host/device hash | NMEA_UNIQUE_NUMBER | --unique-number |
| Logical device key | engine-0 | NMEA_DEVICE_KEY | --device-key |
| Device instance | 0 (8 bits, lower/upper combined) | NMEA_DEVICE_INSTANCE | --device-instance |
| System instance | 0 | NMEA_SYSTEM_INSTANCE | --system-instance |
| Engine instance | 0 | NMEA_ENGINE_INSTANCE | --engine-instance |

Rates must be finite and in (0, 100] Hz. The upper bound is a development input
limit, not a recommendation or claim of bus suitability. Rates affect simulator
TX only; the consumer listens at whatever cadence arrives. `--count` and
`--timeout` (default 5 seconds) support bounded demonstrations and tests. Source
addresses 252–255 cannot be selected. Consumer source-address configuration does
not filter reception; it listens to all sources for supported engine and discovery PGNs.

```sh
NMEA_CAN_CHANNEL=can0 env/bin/python -m nmea_sim.simulator --channel vcan0
NMEA_RAPID_HZ=10 NMEA_DYNAMIC_HZ=2 env/bin/python -m nmea_sim.simulator
```

Before TX without opt-in, the simulator queries the kernel interface kind using
`ip -json -details link show`. Only a verified `vcan` interface is exempt from
`--allow-physical-tx`, regardless of its name. Failure to establish the type
refuses transmission. A physical interface renamed `vcan0` is still guarded.
The approved unassigned test manufacturer 2046 is **always blocked on physical
interfaces**, even with `--allow-physical-tx`. A future physical bench run needs
a legitimately assigned manufacturer identity and the M4 gates. An explicit
opt-in never auto-configures hardware. See
[hardware transition gates](docs/hardware-transition.md) before any bench use.

## Deterministic engine script

The default 50-second cycle includes all required states:

| Cycle time | State | RPM |
| --- | --- | --- |
| 0–2 s | off | 0 |
| 2–4 s | starting | smooth 0 to 750 |
| 4–9 s | idle | 750 |
| 9–19 s | acceleration | smooth 750 to 4500 |
| 19–29 s | cruise | 4500 |
| 29–39 s | deceleration | smooth 4500 to 750 |
| 39–44 s | idle | 750 |
| 44–46 s | deceleration/shutdown | smooth 750 to 0 |
| 46–50 s | off | 0 |

RPM and trim repeat deterministically; engine hours continue across cycles.
Starting-to-shutdown time counts as running time in this synthetic script.
Oil pressure and fuel flow follow RPM and become zero when off. Voltage is
12.6 V when off/cranking and 14.2 V while charging. Coolant warms with accumulated
running time; cooldown is not modeled. Trim ranges from -4 to 12 percent.
Both status words describe a nominal engine with no alarms. Unsupported boost,
oil temperature, coolant/fuel pressure, load and torque remain unavailable.
These are synthetic operating characteristics, not calibrated engine behavior.
Scenario selection and fault injection are not implemented.

## Protocol and evidence

[Protocol matrix](docs/protocol-matrix.md) records payload layouts, references,
unsupported fields, discovery behavior, evidence and remaining conformance gaps.
The encoder/decoder layouts were checked against
[CANboat definitions](https://github.com/canboat/canboat/blob/master/docs/canboat.json)
and [NMEA2000 message implementations](https://github.com/ttlappalainen/NMEA2000/blob/master/src/N2kMessages.cpp).
Their use is not certification or proof of third-party runtime interoperability.

Fast packets support 1–223 payload bytes, three-bit sequence rollover, interleaved
source/PGN/destination/sequence streams, up to 64 buffered assemblies and a
0.75-second absolute packet lifetime. Missing, duplicate, malformed or reordered
fragments discard an assembly; recovery requires a fresh start. TX uses FF
padding; RX accepts a short final frame only when all remaining bytes exist.

[Recorded capture and reproduction instructions](docs/captures/README.md) include
real `candump -L` output and an offline replay test. This evidence confirms CAN
traffic and our consumer's decoding. The M3 capture also includes independently
regenerated CANboat output and a field-by-field validation report.

## Tests

```sh
env/bin/python -m pytest -q -rs
```

Tests cover configuration precedence, rate validation and scheduling, kernel-type
TX guards, identifiers, known vectors, sentinels, every engine phase, running
time, transport damage/timeout/capacity, capture replay and separate processes
on real `vcan0`. Live checks skip with actionable reasons when SocketCAN or
candump is unavailable. Test sources are 201–203 and 215/216/219; engine
capture generation uses 205 and M3 capture generation uses 210/211/220.
Reserve these addresses during testing; other sources may continue running.

Default cadence checks allow ±50 ms per rapid interval and ±0.5 seconds over
an eight-second observation window; dynamic cadence allows ±0.5 seconds over
the same window. Linux scheduling and SocketCAN timestamps are not hard real-time.

M4 baseline verification on 2026-11-13: **368 passed in 12.57s**, no skips, with real
`vcan0` and candump. Restricted-sandbox verification: **364 passed, 4 skipped**
because the live interface is unavailable in that namespace. Saved captures replayed offline; CANboat independently matched 79 M3 messages
across nine PGNs plus 308 full-cycle engine messages during M4. No physical interface was configured or used.

## Device behavior (M3)

At startup the device claims its preferred source, waits at least 250 ms, then
starts engine telemetry and a 6-second heartbeat. Engine time starts with the
first acquired address, continues through conflicts, and is never read by the
consumer. Lower numeric ISO NAME wins. A winning conflict reasserts ownership;
a losing conflict selects the next unobserved address in 0–251 with wraparound.
Telemetry pauses during either claim. Traffic from an unclaimed legacy talker
at our address also causes relocation. Exhaustion emits Cannot Claim from 254
and exits with an actionable error. Duplicate NAME detection stops transmission.
Observed peer addresses are retained conservatively until that NAME moves;
there is no automatic timeout-based reuse of quiet addresses.

NAME uses class 50/function 140 (Propulsion/Engine), marine industry 4, arbitrary
address capability 1, and spare bit 48 = 0. The default 21-bit unique number is
a hash of `/etc/machine-id` and `--device-key`, independent of source address.
It is stable across restarts on the same host; it is not a globally allocated
serial number and hash collisions/cloned machine IDs remain possible. Set a
distinct explicit `--unique-number` (1–2097151) for each simulated device sharing
a bus; use a different device key for another logical node. Changing only the
source address does not change identity. Missing machine ID requires an explicit
unique number. Product serial text is derived from unique number/device instance.

The user-approved manufacturer 2046 is the NMEA2000 library's **unassigned**
open-source convention, not an NMEA-assigned manufacturer or a certified product.
CANboat omits that manufacturer lookup as an out-of-range value; raw NAME still
contains 2046. Product code, protocol version, certification level and hardware
load metadata are unavailable, rather than fabricated. Model/configuration
strings explicitly identify a virtual test device. No Yamaha identity is used.

Directed/global ISO requests for 60928, 126996, 126998 and 126464 are supported.
PGN-list replies advertise separate TX/RX lists. Information requiring ownership
is suppressed during claiming. Unsupported directed requests receive ISO NACK;
unsupported global or other-destination requests are ignored. Engine PGNs are
periodic-only, not supplied on ISO request. Heartbeat is also not ISO-requestable.
Heartbeat counts 0–252 and wraps to 0; controller states are unavailable because
hardware counters are not inspected. Equipment status is operational once claimed.

Heartbeat interval-changing group functions (126208), commanded address (65240),
remote instance/configuration changes and ISO multi-packet transport are not
implemented or advertised. Supported payloads fit fast packets. These limitations
and normative-reference gaps are listed in the protocol matrix; passing virtual
tests does not establish complete standards compliance.

## Reproduce M3 evidence

```sh
env/bin/python scripts/capture_device.py --output /tmp/m3-device.log
```

This uses only verified `vcan0` and reserves addresses 210, 211 and 220. It runs
an independent request peer, simulator process and candump, then checks discovery,
negative requests, winning/losing conflicts, claim gating and heartbeat. See
[recorded results and CANboat commands](docs/captures/README.md).

## M4 interoperability and bench transition

CANboat independently matched 308 engine messages across a complete 51-second
cycle, in addition to the 79 M3 discovery/conflict messages. Full-cycle capture,
independent JSON, binary/input/output hashes and field ranges are saved under
`docs/captures/`. CANboat remains an optional validation tool, not a runtime
dependency. See [M4 results and reproduction](docs/interop-m4.md).

```sh
env/bin/python -m nmea_sim.preflight --channel vcan0
env/bin/python scripts/capture_cycle.py --output /tmp/m4-cycle.log
```

Preflight reads interface metadata without a CAN socket, configuration changes
or transmission. Its software result never authorizes hardware TX. The bench
guide now targets the user-specified Waveshare 2-CH CAN HAT (Isolated) and Pi 3,
including conditional driver setup, 250 kbit/s commands and measured wiring/
power/termination gates. The [physical acceptance record](docs/bench-acceptance.md)
is deliberately unfilled: assigned identity, actual can0/ACK-peer testing and
Garmin model/firmware acceptance remain pending. No physical interface was
configured or used. No network service is planned. The pre-existing empty
`sim2k.py` is unused.


## M5 native desktop dashboard

A native PySide6 / Qt Quick dashboard now receives SocketCAN directly. It reuses
our decoder/fast-packet transport, supports source/engine selection, analog RPM
and temperature, digital engine readings, per-PGN stale detection, reported
status alerts and a bounded/filterable raw CAN diagnostic panel. It is receive-only
and has no simulator-state shortcut or network backend.

```sh
env/bin/python -m pip install -e '.[test,dashboard]'
# X11 desktops on this host also require: sudo apt-get install libxcb-cursor0
env/bin/python dashboard.py --channel vcan0
# In another terminal:
env/bin/python -m nmea_sim.simulator --channel vcan0 --unique-number 1
```

Use `--channel can0` for the receive-only dashboard after external hardware setup;
no application edits or TX opt-in are needed. Qt is an optional GUI dependency;
the simulator and console consumer remain usable without it.
[Installation, diagnostics, tests and troubleshooting](docs/dashboard.md) ·
[Native live screenshot](docs/captures/m5-dashboard-live.png).

M5 verification: **396 passed in 21.53s**, with real vcan0 access and no skips.
Native X11/xcb rendering was verified in Xvfb with a process-local copy of the
missing cursor library. Install libxcb-cursor0 normally for desktop launch on
this host; see the dashboard guide for details. Physical Pi/CAN/Garmin acceptance
remains pending.
