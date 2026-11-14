NMEA 2000 Engine Simulator — Codex Implementation Plan
Status: Implementation specification · Updated: 2026-11-13

Objective
Build a Python marine-engine simulator that is consumed entirely through the NMEA 2000 protocol. It must publish standards-conformant NMEA 2000 traffic over Linux SocketCAN and be discoverable and interpretable by an independent NMEA 2000 stack. No web APIs, WebSockets, MQTT, Signal K endpoints, or custom telemetry transport are part of this project.

Start with vcan0 for development. Substitute the Waveshare hardware can0 later by configuration only. Simulate a generic single-outboard engine with operating characteristics inspired by a Yamaha F115; do not impersonate Yamaha or assert proprietary Yamaha protocol compatibility.

Hard requirements
Only telemetry output: NMEA 2000 CAN traffic, using 29-bit extended CAN identifiers, correct PGN construction, NMEA 2000 field encodings, units, scaling, unavailable-value sentinels, priorities, and timing.
Network visibility: Clients on the same SocketCAN interface can consume messages. vcan0 is local to the Linux host/network namespace; it is not a LAN service. To serve a remote machine later, use a dedicated CAN-to-network bridge/gateway carrying NMEA 2000 frames, with its transport and safety specified separately. Do not silently introduce an HTTP API.
Configuration: --channel overrides NMEA_CAN_CHANNEL, which defaults to vcan0. Both simulator and consumer must use the same configuration. A separate explicit --allow-physical-tx opt-in is required for transmission on can0 or other non-virtual interfaces.
Device behavior: Implement ISO address claiming, stable unique NAME, device instance and engine instance, and relevant ISO request/response behavior. Product/configuration information and supported-PGN reporting must use standards-correct payloads and transport. Avoid claiming full NMEA certification without conformance testing.
Transport: Correctly implement NMEA 2000 fast-packet segmentation and reassembly for PGNs that require it, including sequence handling, length checks, timeouts, and interleaved traffic.
Independence: Simulator and consumer are separate processes. Consumer must derive values exclusively from received NMEA 2000 CAN frames, not shared Python state, files, or a simulator-specific endpoint.
Safety: Never inject simulated engine traffic into an operational boat network. Physical tests use an isolated, properly terminated, powered, fused NMEA 2000 bench backbone with no live engine attached. Avoid source-address conflicts.
Testing: Include deterministic encoder/decoder tests, independent interoperability checks, packet captures, and hardware-readiness gates. Do not describe the system as “100% compliant” without external validation and, where applicable, NMEA certification.
Architecture
 Engine scenario/state model
           |
 NMEA 2000 device + PGN encoder + fast-packet transport
           |
    SocketCAN TX (vcan0 by default; can0 later)
           |
   ===== NMEA 2000 CAN traffic =====
           |
 Independent SocketCAN RX + NMEA 2000 protocol decoder
           |
      Console diagnostics / tests

NO REST API | NO WebSocket | NO MQTT | NO proprietary telemetry protocol
The console client is a diagnostic tool, not a second telemetry protocol. Its input must be the same NMEA 2000 messages a third-party consumer sees.

Protocol scope
Phase 1: engine rapid update
PGN 127488 — Engine Parameters, Rapid Update: engine instance, RPM, boost pressure (unavailable if not modeled), trim (or unavailable). Verify exact field layout and resolution against authoritative NMEA 2000 field definitions before coding.
Emit at a configurable rate (default 5 Hz).
Use extended CAN identifiers with correct PDU1/PDU2 PGN handling.
Provide a simple engine state machine: off, starting, idle, cruise, acceleration/deceleration. Use deterministic seeds or scripted scenarios for tests.
Phase 2: engine dynamic parameters
PGN 127489 — Engine Parameters, Dynamic: supported engine measurements such as temperature, oil pressure, alternator voltage, fuel rate, engine hours, status flags. Encode unmodeled measurements as unavailable; do not fabricate measurements just to fill fields.
Implement and test NMEA 2000 fast-packet fragmentation/reassembly. Standard CAN 2.0 frames remain 8 bytes or less.
Validate all offsets, units, resolutions, reserved fields, and sentinel values using a trusted PGN definition source.
Emit at a configurable rate (default 1 Hz).
Phase 3: device identity and interoperability
PGN 60928 ISO Address Claim; implement 64-bit NAME correctly, a stable unique identity, conflict handling, and safe source-address selection.
PGN 59904 ISO Request; respond to applicable requests for supported information.
PGN 126996 Product Information and PGN 126998 Configuration Information, with correct fast-packet formatting.
PGN 126464 PGN List as applicable, with correct fast-packet formatting.
Consider PGN 126993 Heartbeat if required for target consumers, with correct semantics.
Document mandatory versus optional behavior and evidence for each. Never use an invented manufacturer code or misrepresent the device as certified hardware; use a suitable development identity and explicitly document any interoperability limitations.
Phase 4: optional additional PGNs
PGN 127508 Battery Status, PGN 127505 Fluid Level, only if those are modeled as separate simulated devices/sensors with appropriate identities and field semantics.
Keep engine telemetry separate from vessel or battery telemetry; do not imply these originate from the engine unless that is protocol-correct.
Repository layout
nmea-engine-simulator/
  README.md
  pyproject.toml
  src/nmea_sim/
    config.py
    engine_model.py
    can_transport.py
    identifiers.py
    pgn_127488.py
    pgn_127489.py
    fast_packet.py
    device.py
    simulator.py
    consumer.py
  tests/
    test_config.py
    test_identifiers.py
    test_pgn_127488.py
    test_pgn_127489.py
    test_fast_packet.py
    test_device_protocol.py
    test_vcan_integration.py
  docs/
    protocol-matrix.md
    hardware-transition.md
    captures/
Keep device and transport abstractions independent of the selected CAN interface. Use python-can, can-utils, and pytest; add dependencies only if justified.

CLI and environment
# On Linux, once per boot (or configure persistently later)
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan  # skip if it already exists
sudo ip link set vcan0 up

# Defaults to vcan0
python -m nmea_sim.simulator
python -m nmea_sim.consumer

# Environment override
NMEA_CAN_CHANNEL=vcan0 python -m nmea_sim.simulator

# CLI wins over environment
NMEA_CAN_CHANNEL=can0 python -m nmea_sim.simulator --channel vcan0

# Physical CAN TX requires a separate explicit opt-in and safety checks
python -m nmea_sim.simulator --channel can0 --allow-physical-tx
A consumer should not need a transmit opt-in if it is strictly receive-only. Fail with a clear error if an interface is missing or the operator attempts physical transmission without opting in. Never auto-create or reconfigure physical can0 from the simulator.

Implementation milestones and acceptance criteria
M0 — Project skeleton and virtual bus
Python package, documented setup, shared configuration, logging, unit-test scaffolding.
Bring up vcan0, verify with ip -details link show vcan0 and candump vcan0.
Pass: both processes accept --channel / NMEA_CAN_CHANNEL; precedence tests pass; no network server or web dependency exists.
M1 — Real PGN 127488 traffic
Implement 29-bit identifier generation and PGN extraction; independently encode and decode PGN 127488.
Simulated RPM changes realistically; receiver reports decoded RPM and engine instance.
Capture traffic with candump -L vcan0 and include a reproducible test fixture.
Pass: separate consumer reads only CAN traffic; correct PGN, source, priority, length, scaling and unavailable values; 5 Hz rate within documented tolerance.
M2 — PGN 127489 and fast-packet
Encode engine dynamic parameters with authoritative field definitions.
Add reusable fast-packet encoder/decoder with boundary and malformed-frame tests.
Pass: reassembled payload matches original bytes; independent consumer decodes all modeled values; concurrent fast-packet streams do not corrupt one another.
M3 — Discoverable NMEA 2000 device
Implement address claim, NAME, ISO requests, supported-PGN reporting, product/configuration data, and applicable heartbeat behavior.
Pass: an independent NMEA 2000 parser recognizes device identity and both engine PGNs; request/response behavior is verified using captures and documented expectations. Any unsupported protocol feature is disclosed.
M4 — Interoperability and physical transition
Run independent decode validation (prefer a third-party NMEA 2000 stack, not solely the project's own decoder).
Record actual capture files and field-level results.
Document isolated bench wiring, power, termination, source-address collision precautions, and Waveshare can0 configuration at 250 kbit/s.
Pass: switching vcan0 to can0 requires no application-code edits, only configuration; hardware transmission remains blocked without explicit opt-in. Garmin display interoperability is a separate physical acceptance test, not assumed from vcan0 tests.


## Milestone M5 — Native NMEA 2000 Instrument Dashboard

### Objective

Build a native Linux desktop instrument dashboard that consumes and
visualizes live NMEA 2000 engine telemetry through SocketCAN.

The dashboard must operate as an independent NMEA 2000 client.
It must not communicate directly with the engine simulator or use
REST APIs, WebSockets, MQTT, or other intermediary protocols.

The dashboard must be compatible with both simulated NMEA 2000
traffic on `vcan0` and physical NMEA 2000 traffic on `can0`.

### Technology

- Python 3
- PySide6 (Qt Quick/QML preferred)
- python-can / SocketCAN
- Existing NMEA 2000 decoder components
- Native Linux desktop application

### Functional Requirements

#### 1. Engine Instrument Display

Implement a marine-style instrument dashboard featuring:

| Instrument | Source PGN | Display |
|------------|------------|---------|
| Engine RPM | 127488 | Analog tachometer |
| Engine Temperature | 127489 | Analog gauge |
| Alternator Voltage | 127489 | Digital |
| Oil Pressure | 127489 | Digital |
| Fuel Rate | 127489 | Digital |
| Engine Hours | 127489 | Digital |
| Engine Trim | 127488 | Digital or bar gauge |

Use a modern marine multifunction display aesthetic with
a dark background, high-contrast instruments, and clear labels.

#### 2. NMEA 2000 Integration

- Consume NMEA 2000 messages directly through SocketCAN.
- Reuse the project's existing PGN decoding implementation.
- Support NMEA 2000 fast-packet reassembly.
- Identify engine instances and CAN source addresses.
- Support configurable CAN interfaces.
- Do not access simulator state or internal variables.
- Do not introduce web APIs or network services.

Configuration precedence:

1. `--channel` command-line argument
2. `NMEA_CAN_CHANNEL` environment variable
3. Default: `vcan0`

Example:

```bash
python dashboard.py --channel vcan0
python dashboard.py --channel can0
```

#### 3. Real-Time Instrument Updates

- Update gauges as new NMEA 2000 messages arrive.
- Maintain responsive rendering independent of CAN reception.
- Use Qt signals/slots to communicate between the CAN
  receiver and UI.
- Display unavailable measurements as `--`, not zero.
- Detect stale telemetry and indicate lost communication.
- Display current engine instance and source address.

#### 4. Engine Status and Alerts

Provide visual indicators for:

- Engine running/stopped
- High engine temperature
- Low oil pressure
- Low alternator voltage
- Engine warning conditions
- CAN connection status

Use decoded NMEA 2000 engine status fields where available.

Do not infer actual engine faults solely from arbitrary
thresholds. Any configurable diagnostic thresholds must
be clearly distinguished from NMEA 2000-reported alarms.

#### 5. Diagnostic View

Provide a separate diagnostic panel containing:

- Raw CAN identifier
- Decoded PGN
- Source address
- Timestamp
- Raw payload (hexadecimal)
- Decoded field values
- Message count and receive rate
- Fast-packet reassembly errors

Allow filtering by PGN and source address.

#### 6. Application Architecture

Maintain separation between:

1. SocketCAN transport
2. NMEA 2000 protocol decoding
3. Engine telemetry state management
4. Dashboard presentation

The UI must not contain PGN decoding logic.

The dashboard must remain functional if the engine simulator
is replaced by a real NMEA 2000 engine interface.

### Testing Requirements

Implement automated tests covering:

- PGN 127488 decoding and gauge updates
- PGN 127489 fast-packet reassembly
- Missing and unavailable sensor values
- Stale telemetry detection
- Multiple engine instances and source addresses
- Engine status and warning indicators
- Invalid or malformed CAN frames
- CAN interface configuration precedence
- Graceful handling of CAN interface failures

Provide an integration test using `vcan0` with the engine
simulator and dashboard running as separate processes.

### Acceptance Criteria

- [ ] Dashboard launches as a native Linux application.
- [ ] Dashboard receives data directly from `vcan0`.
- [ ] RPM and engine telemetry update in real time.
- [ ] All displayed values originate from decoded NMEA 2000 PGNs.
- [ ] Analog gauges respond smoothly to changing values.
- [ ] Missing data is clearly distinguished from zero.
- [ ] Communication loss is detected and displayed.
- [ ] Diagnostic view displays raw and decoded CAN traffic.
- [ ] Dashboard operates independently of the simulator.
- [ ] Switching to `can0` requires no application code changes.
- [ ] No web APIs, HTTP servers, or WebSocket services are introduced.
- [ ] Automated tests pass.

### Deliverables

1. Native PySide6 instrument dashboard.
2. Reusable SocketCAN receiver integration.
3. Engine telemetry state model.
4. Diagnostic CAN traffic viewer.
5. Automated unit and integration tests.
6. README documenting installation, configuration,
   operation, and troubleshooting.

### Out of Scope

- Engine control or command transmission
- Proprietary Garmin protocols
- Physical NMEA 2000 gateway hardware development
- Cloud connectivity
- Web-based dashboards
- Remote telemetry APIs
- Persistent historical telemetry storage

### Implementation Guidance for Codex

Implement this milestone only after the simulator's
NMEA 2000 PGN encoding and independent decoding components
are functional and validated.

Reuse existing transport and decoding components rather
than creating duplicate implementations.

Prioritize protocol correctness, separation of concerns,
and testability over visual polish.

The completed dashboard should serve as both a simulated
engine instrument display and a foundation for a future
physical NMEA 2000 diagnostic application.


Explicit exclusions
HTTP/REST, WebSocket, MQTT, Signal K service, dashboard backend, JSON-over-LAN, or custom TCP/UDP telemetry.
Engine command/control, starter actuation, proprietary Yamaha PGNs, unsafe fault injection, or connection to a running vessel network.
Claims of full NMEA 2000 certification based only on self-tests.
Guidance for Codex
Implement M0 and M1 first. Before encoding a PGN, confirm its authoritative byte layout and units; if a trusted definition is unavailable, document the gap instead of guessing. Add tests, run them, capture real vcan0 frames, and report commands/results. Stop for review before M2. Keep the output protocol exclusively NMEA 2000 from the start. No web API scaffolding.
