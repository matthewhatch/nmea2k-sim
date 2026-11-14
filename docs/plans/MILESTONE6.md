
# Milestone M6 — NMEA 2000 Ethernet Transport

## Objective

Enable the existing NMEA 2000 instrument dashboard to consume
live NMEA 2000 traffic from a remote Raspberry Pi over Ethernet.

The Raspberry Pi will act as a SocketCAN-to-Ethernet gateway,
allowing multiple independent clients to monitor CAN traffic
originating from the simulated engine or physical NMEA 2000 devices.

Preserve the existing NMEA 2000 protocol implementation.
Do not introduce REST APIs, WebSockets, MQTT, RabbitMQ, or
proprietary telemetry schemas.

## Architecture

NMEA 2000 Sources
  - Simulated engine
  - Physical NMEA 2000 devices (future)
          |
          v
Raspberry Pi SocketCAN
  - vcan0: virtual simulation
  - can0: physical CAN interface
          |
          v
SocketCAN Ethernet Gateway
  - Preferred: socketcand
  - TCP transport
  - Multiple concurrent clients
          |
          v
Remote Dashboard
  - SocketCAN transport (existing)
  - Remote TCP transport (new)
          |
          v
Existing NMEA 2000 Decoder
          |
          v
Instrument Dashboard

## M6.1 — Transport Abstraction

Introduce a transport interface shared by local and remote
CAN receivers.

Requirements:

- Preserve existing local SocketCAN functionality.
- Support vcan0 and can0.
- Add remote TCP transport.
- Reuse the existing NMEA 2000 decoder.
- Do not duplicate PGN decoding logic.
- Keep transport implementation independent of the UI.
- Maintain a consistent CAN frame representation.

The internal frame representation must preserve:

- 29-bit CAN arbitration identifier
- Extended-frame flag
- DLC and payload bytes
- Frame ordering
- Receive timestamp
- Source transport metadata

Remote receive timestamps may reflect gateway or client
receipt time depending on transport capabilities. Document
timestamp semantics.

## M6.2 — SocketCAN Ethernet Gateway

Evaluate and implement socketcand as the preferred gateway.

Requirements:

- Run on Raspberry Pi Linux.
- Support vcan0 initially.
- Support can0 through configuration.
- Support multiple concurrent TCP clients.
- Preserve CAN frame contents.
- Support NMEA 2000 extended CAN identifiers.
- Preserve ordering within each client stream.
- Operate without a web server or HTTP API.
- Restrict access to trusted LAN clients.

Before implementation, verify:

- socketcand availability and compatibility.
- Supported socketcand protocol and framing.
- Compatibility with the project's Python dependencies.
- Ability to receive frames without transmitting to CAN.
- Multi-client behavior and limitations.

If socketcand is unsuitable, document the incompatibility
and propose an established alternative before introducing
a custom network protocol.

## M6.3 — Remote Dashboard Transport

Add a remote CAN transport implementation.

Configuration:

--transport socketcan
--channel vcan0

--transport socketcand
--host <gateway-ip>
--port <gateway-port>
--channel vcan0

Environment variables:

NMEA_TRANSPORT=socketcan
NMEA_CAN_CHANNEL=vcan0
NMEA_GATEWAY_HOST=
NMEA_GATEWAY_PORT=29536

Configuration precedence:

1. Command-line arguments
2. Environment variables
3. Application defaults

Requirements:

- Connect to the configured gateway.
- Implement the actual socketcand protocol handshake
  and frame parsing; do not assume raw CAN frames are
  sent directly over TCP.
- Feed received frames into the existing decoder.
- Reconnect automatically after connection loss.
- Use bounded buffering to prevent unlimited memory use.
- Provide clean startup and shutdown.
- Avoid blocking the dashboard UI thread.
- Support multiple dashboard instances.

## M6.4 — Connection Status and Diagnostics

Extend the dashboard diagnostics to show:

- Transport type
- CAN channel
- Gateway host and port
- Connection state
- Frames received
- Frames per second
- Last received frame timestamp
- Reconnection attempts
- Transport and parsing errors

Connection states:

- Disconnected
- Connecting
- Connected
- Reconnecting
- Error

Connection state must be distinguished from telemetry state.

A connected TCP socket does not necessarily mean valid
NMEA 2000 telemetry is being received.

Existing stale-data detection must continue to work.

## M6.5 — Read-Only Operation

Remote dashboard connections must be receive-only.

Requirements:

- No CAN transmission from the dashboard.
- No remote engine commands.
- No gateway write operations initiated by the dashboard.
- No automatic bridging between vcan0 and can0.
- No forwarding of simulated traffic onto the physical
  NMEA 2000 backbone.

Important:

Client-side read-only behavior does not guarantee that the
gateway rejects writes from other clients.

Document socketcand's actual access-control capabilities.
If server-side read-only enforcement is unavailable, isolate
the gateway on a trusted network and explicitly document
that limitation.

## M6.6 — Testing

### Unit Tests

- Transport configuration precedence
- CAN frame parsing
- Extended 29-bit CAN identifiers
- Payload integrity
- Invalid and truncated TCP messages
- Connection state transitions
- Reconnection behavior
- Bounded buffering
- Clean shutdown

### Integration Tests

Using vcan0:

1. Start the existing engine simulator.
2. Start the SocketCAN Ethernet gateway.
3. Connect a remote dashboard.
4. Verify reception of PGN 127488.
5. Verify PGN 127489 fast-packet reassembly.
6. Confirm instrument values match transmitted data.
7. Connect a second independent client.
8. Verify both clients receive telemetry.
9. Disconnect and restart the gateway.
10. Verify automatic reconnection and telemetry recovery.

### Regression Tests

- Existing local vcan0 dashboard remains functional.
- Existing local can0 configuration remains supported.
- Existing NMEA 2000 decoding tests continue to pass.
- No changes to simulator PGN encoding are required.

## M6.7 — Deliverables

1. Transport abstraction or adapter.
2. Socketcand-compatible remote receiver.
3. Updated dashboard configuration.
4. Connection status and diagnostic indicators.
5. Gateway installation and configuration instructions.
6. Automated unit and integration tests.
7. Updated README and architecture documentation.
8. Documented gateway limitations and security assumptions.

## Acceptance Criteria

- [ ] Existing local SocketCAN operation still works.
- [ ] Raspberry Pi exposes vcan0 traffic over Ethernet.
- [ ] Remote dashboard receives native CAN frames.
- [ ] PGN 127488 decodes correctly.
- [ ] PGN 127489 fast-packet messages decode correctly.
- [ ] Two independent remote clients can receive telemetry.
- [ ] Dashboard reconnects after gateway interruption.
- [ ] Missing telemetry is detected and displayed.
- [ ] Remote dashboard does not transmit CAN frames.
- [ ] Simulated traffic is not bridged to physical can0.
- [ ] Gateway access is restricted to the trusted LAN.
- [ ] Automated tests pass.
- [ ] No web API or message broker is introduced.

## Out of Scope

- Cloud connectivity
- Internet-facing gateway access
- Remote CAN transmission
- NMEA 2000 device control
- CAN-to-CAN bridging
- Signal K conversion
- Historical telemetry storage
- Web dashboards
- Message queues
- Physical Garmin interoperability testing

## Definition of Done

The engine simulator runs on the Raspberry Pi and publishes
valid NMEA 2000 traffic to vcan0.

A dashboard running on a separate Linux computer connects
over Ethernet, receives the CAN frames, decodes the same
PGNs as the local dashboard, and displays live engine
instrument values.

No application-level telemetry API is required.
