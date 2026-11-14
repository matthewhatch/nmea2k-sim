# Protocol matrix

Status: M0–M3 implemented for virtual development. No NMEA certification or
physical-network conformance is claimed. M4 full-cycle independent validation
and target-specific bench preparation are recorded in interop-m4.md; physical
acceptance remains pending.

References checked on 2026-11-13:

- [CANboat 9.2.0 definitions, pinned commit](https://github.com/canboat/canboat/tree/2a42e004e01094b25049dddf737277f33c324ff1/database/pgns): layouts, priorities, NAME/class/function lookups, fixed/LAU string types and PGN lists.
- [NMEA2000 device implementation](https://github.com/ttlappalainen/NMEA2000/blob/master/src/NMEA2000.cpp): claim wait, lower-NAME arbitration, 0–251 source selection, ISO request dispatch, PGN lists and heartbeat counter rollover.
- [NMEA2000 message implementations](https://github.com/ttlappalainen/NMEA2000/blob/master/src/N2kMessages.cpp): engine fields.
- [NMEA2000 identity API documentation](https://ttlappalainen.github.io/NMEA2000/pg_lib_ref.html): 2046 is explicitly an unassigned open-source convention, not an NMEA-issued manufacturer code.
- [NMEA manufacturer/product identity information](https://www.nmea.org/nmea-2000.html): assignment and certification are separate from this project's tests.

These public implementations are trusted layout references, not a licensed
normative standard or an external certification audit. CANboat independently
parsed the recorded M3 exchanges; field-level comparisons passed for 79 decoded
messages across nine PGNs (including requests). Source/raw capture, exact tool
revision, commands, output and limitations are recorded under `docs/captures/`.

| PGN | Role / project requirement | Implementation and evidence |
| --- | --- | --- |
| 59392 | Supporting negative acknowledgement | Directed unsupported requests get NACK; global unsupported requests are silent; vectors/live capture/CANboat |
| 59904 | M3 required: ISO Request | Directed and global requests; strict three-byte PGN; ignore malformed and other-destination requests; unit/live/CANboat |
| 60928 | M3 required: NAME/address ownership | Stable identity, 250 ms claiming, numeric arbitration, relocation, duplicate/exhaustion fail-closed; unit/live/capture/CANboat |
| 126464 | M3 required: supported PGNs | Separate TX/RX fast packets, function 0/1 and repeated LE 24-bit PGNs; vectors/capture/CANboat |
| 126993 | Plan calls for applicability decision; enabled for presence supervision | Fixed 6 s interval, priority 7, counter 0–252; unit/capture/CANboat; interval group functions unsupported |
| 126996 | M3 required: product identity | 134-byte fast packet, four fixed 32-byte ASCII fields, unavailable uncertified metadata; vectors/live/CANboat |
| 126998 | M3 required: configuration identity | Three LAU strings, including length/control bytes; ASCII TX, ASCII/UTF-16LE RX; vectors/live/CANboat |
| 127488 | M1 required: rapid engine | 8 bytes, priority 2, default configurable 5 Hz; vectors/live/capture/CANboat |
| 127489 | M2 required: dynamic engine | 26 bytes, priority 2, default configurable 1 Hz; vectors/live/capture/CANboat |

“Required” above means required by this project's updated milestone specification;
it does not assert that every listed feature is universally mandatory in every
NMEA device class. A licensed-standard conformance review is still an M4 gate.

## Development identity policy

The user explicitly approved 2046 as a **vcan-only test exception** to the plan's
assigned-manufacturer requirement. It is never described as an assigned code.
The transport guard verifies kernel interface kind and blocks 2046 on physical
interfaces even with physical TX opt-in. Other manufacturer values must be
operator-supplied, legitimately assigned values; the program cannot verify
ownership of an assignment. Reserved 2045/2047 are rejected by configuration.

Default NAME fields: manufacturer 2046, class 50/function 140 (Propulsion/Engine),
industry 4, system/device instance 0, arbitrary-address capability 1, spare bit
48 = 0. Device instance combines lower 3 and upper 5 bits. The 21-bit unique
number is stable from host machine-id plus logical device key or explicitly
configured; do not run two nodes with the same identity. Hash uniqueness is
local/operator-managed, not globally guaranteed. NAME is independent of claimed
source address. Equal NAME received from another socket stops the simulator.

Product strings identify `NMEA Engine Sim TEST`, software `0.1.0`, virtual
development and a serial derived from unique number/device instance. Version,
product code, certification and load-equivalency fields use unavailable values.
In particular certification zero is not used: CANboat interprets zero as Level A.
CANboat also omits the 2046 manufacturer lookup as out-of-range; that is an
expected development-identity limitation, not a successful manufacturer lookup.
The raw NAME, class/function, instances and serial are still verifiable.

## Addressing and requests

Claim at preferred source, wait at least 250 ms, then permit application TX.
Conflicting lower NAME wins. A winner reasserts its claim and waits; a loser
searches observed-free sources 0–251 with wraparound, claims and waits again.
Non-claim traffic using our address also causes relocation. Peer observations
are bounded to the address space and retained conservatively until that NAME
moves or emits Cannot Claim. All addresses occupied: emit Cannot Claim at 254
and exit with no engine telemetry. The consumer never transmits or participates
in address arbitration.

| Requested PGN | Owned-address response | Other conditions |
| --- | --- | --- |
| 60928 | Broadcast NAME, even for directed request | Also respond while claiming, or with source 254 in the Device cannot-claim state |
| 126996 | Broadcast fast-packet product data | Suppressed before address ownership |
| 126998 | Broadcast fast-packet configuration strings | Suppressed before address ownership |
| 126464 | TX and RX list fast packets | Suppressed before address ownership |
| Unsupported, including periodic-only engine/heartbeat PGNs | Directed request: NACK to requester | Global unsupported request: silent |

These information PGNs are PDU2 broadcasts; a directed ISO request does not make
their response addressable. ISO acknowledgements are PDU1 and retain requester
destination. Lists advertise TX 59392/60928/126464/126993/126996/126998/127488/127489
and RX 59904/60928. Observing other traffic for collision detection is not an
advertisement that the device implements those PGNs' application semantics.

Heartbeat is emitted after claiming and every 6 seconds thereafter, including
counter rollover. Interval is encoded in milliseconds, priority is 7, reserved
bits are ones, controller states unavailable, equipment operational. It is not
ISO-requestable. CANboat's heartbeat definition and NMEA2000's counter code are
the implementation references. Interval-changing group functions are not supported;
therefore heartbeat support alone is not a claim of complete heartbeat conformance.

## Known protocol limitations

PGN 126208 group functions (including instance/configuration changes and heartbeat
interval requests), commanded address 65240, ISO multi-packet transport, remote
engine commands, proprietary PGNs and physical acceptance are out of scope.
Information replies are on request, not an automatic product-info broadcast at
startup. No timeout-based address-table recycling is implemented. The executable
exits after Cannot Claim, so it does not remain alive as an unaddressed node.
No physical hardware load/controller-state measurements or certification are
fabricated. The software's default rates follow the plan rather than a claimed
certification profile. No network API or custom telemetry transport exists.

## PGN 127488

Zero-based offsets; all multi-byte fields little endian.

| Bytes | Field | Type / resolution | Simulation |
| --- | --- | --- | --- |
| 0 | Instance | unsigned 8-bit | 0 |
| 1–2 | Speed | unsigned 16-bit / 0.25 RPM | scripted |
| 3–4 | Boost | unsigned 16-bit / 100 Pa | unavailable |
| 5 | Trim | signed 8-bit / 1 percent | scripted -4 to 12 |
| 6–7 | Reserved | FF FF | reserved |

## PGN 127489

| Bytes | Field | Type / resolution | Simulation |
| --- | --- | --- | --- |
| 0 | Instance | unsigned 8-bit | 0 |
| 1–2 | Oil pressure | unsigned 16-bit / 100 Pa | follows RPM |
| 3–4 | Oil temperature | unsigned 16-bit / 0.1 K | unavailable |
| 5–6 | Coolant temperature | unsigned 16-bit / 0.01 K | warms with running time |
| 7–8 | Alternator voltage | signed 16-bit / 0.01 V | charging/off values |
| 9–10 | Fuel rate | signed 16-bit / 0.1 L/h | follows RPM |
| 11–14 | Running time | unsigned 32-bit / 1 second | public engine_hours converts to hours |
| 15–16 | Coolant pressure | unsigned 16-bit / 100 Pa | unavailable |
| 17–18 | Fuel pressure | unsigned 16-bit / 1000 Pa | unavailable |
| 19 | Reserved | FF | reserved |
| 20–21 | Status 1 | 16-bit flags | nominal zero |
| 22–23 | Status 2 | 16-bit flags | nominal zero |
| 24 | Load | signed 8-bit / 1 percent | unavailable |
| 25 | Torque | signed 8-bit / 1 percent | unavailable |

Numeric unavailable codes are the maximum positive integer for the field type;
error/reserved codes are that value minus one/two. Signed trim unavailable is
7F, signed voltage/fuel unavailable is 7FFF, unsigned words use FFFF, and the
unsigned running-time field uses FFFFFFFF. All three numeric sentinel codes
decode to null. Status words retain all bits and have no numeric sentinels.
Unknown status-2 bits are preserved even when no display name exists.

Integer quantization uses nearest-integer rounding. Reference nominal intervals
are 100 ms (rapid) and 500 ms (dynamic); this plan explicitly chooses defaults
of 200 ms and 1000 ms and makes them configurable. Those development defaults
must not be represented as evidence of timing conformance for a certified node.

## Module boundaries

`device.py` contains the clock-injected claim/request state machine and outgoing
CAN-frame descriptions. `device_protocol.py` contains wire codecs.
`simulator.py` owns one RX/TX SocketCAN socket, processes protocol traffic and
gates model encoding on device ownership. `consumer.py`/`receiver.py` decode
only received frames. `can_id.py` and `transport.py` fulfill the identifier and
transport roles shown as `identifiers.py`/`can_transport.py` in the plan.
