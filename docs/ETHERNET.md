# Remote dashboard over socketcand (M6)

## Technical spike and decision

The gateway was not installed on the development host. We fetched and compiled
upstream socketcand 0.6.1 at commit
`6dd5d33d4645ab221e8cd265c08607366e21ddf1`. A real loopback TCP test against
kernel vcan0 completed the handshake for two simultaneous clients and delivered
identical extended identifier `09F20023`, eight payload bytes, and timestamps to both.
This is a single Linux host test, not a Raspberry Pi or physical Ethernet test.

Primary sources:
- [upstream protocol](https://github.com/linux-can/socketcand/blob/6dd5d33d4645ab221e8cd265c08607366e21ddf1/doc/protocol.md)
- [RAW implementation](https://github.com/linux-can/socketcand/blob/6dd5d33d4645ab221e8cd265c08607366e21ddf1/src/state_raw.c)
- [listener and client processes](https://github.com/linux-can/socketcand/blob/6dd5d33d4645ab221e8cd265c08607366e21ddf1/src/socketcand.c)

The server sends `< hi >`; the client sends `< open vcan0 >`, waits for `< ok >`,
sends `< rawmode >`, and waits for another `< ok >`. Only then does it receive
`< frame 09F20023 seconds.microseconds 00E02EFFFFFCFFFF >`. TCP reads may split
or combine any of these records. RAW mode is important: BCM subscriptions can
suppress or throttle frames, which would break fast-packet reassembly.

A restart experiment also found that this upstream revision guards listener
`SO_REUSEADDR` with `#ifdef DEBUG`. A release build can exit with "Address already
in use" until TCP TIME_WAIT expires after shutdown. The build command below adds
`-DDEBUG` to enable reuse; this does not add receive-only enforcement. With a release
package, retry starting the gateway for up to 75 seconds. The integration test
handles this limitation explicitly. A service should use `Restart=on-failure` and
`RestartSec=2` so a temporary bind failure does not leave it permanently offline.

The server forks a process and opens a CAN socket for each client. Clients have
independent streams, not a competing-consumer queue. Ordering is preserved within
each connection; there is no replay, sequence numbering, delivery guarantee across
reconnections, or global ordering across clients. Slow consumers can lose data at
kernel/server buffers; upstream RAW forwarding uses `send()` without retrying a
short write. The client bounds memory and reports malformed records but cannot
prove that no frame was lost upstream. No custom network protocol was introduced.

Python 3.11 and the pinned python-can 4.6.1 are compatible. Its installed socketcand
backend was inspected: handshake uses single `recv()` calls, EOF is not treated as
connection loss, connection retries are not paced, and the public API permits CAN
transmission. The small receive-only adapter therefore implements the established
socketcand wire protocol directly, retaining python-can `Message` and the existing
`Decoder`. No decoder or simulator encoding changes were needed.

## Architecture and operational behavior

`vcan0 (or configured can0) -> socketcand RAW TCP -> receive transport -> Decoder
-> existing telemetry store -> PySide6 dashboard`. Local operation uses the same
receive interface around the existing SocketCAN opener and the same decoder.
Transport code has no Qt dependency. The simulator remains a separate process.

Defaults are `--transport socketcan --channel vcan0`. Remote usage requires
`--transport socketcand --host ADDRESS`; `--port` defaults to 29536. CLI overrides
`NMEA_TRANSPORT`, `NMEA_CAN_CHANNEL`, `NMEA_GATEWAY_HOST`, `NMEA_GATEWAY_PORT`,
which override defaults. `--channel can0` selects an already configured physical
interface for reception; it never creates a bridge or starts a simulator.

The worker handles all I/O and decoding off the UI thread. Remote failures retry
with backoff from 0.2 to 2 seconds. A new connection gets a new decoder to prevent
combining fast-packet fragments across outages. Partial TCP records are discarded.
The adapter holds at most 4096 input bytes; oversize/invalid protocol records cause
a diagnosed disconnect/retry. There are at most 256 pending UI events plus one
queued batch of at most 256. Old pending UI events are dropped with a counter;
decoding occurs before that drop. The diagnostic history is capped at 200 records.
This is a live monitor, not a lossless recorder.

TCP connect and each handshake step have one-second timeouts; receive polling is
50 ms and retry sleep is interruptible. OS hostname resolution can exceed those
timeouts; use a numeric gateway IP for predictable shutdown. Linux TCP keepalive
uses 10 seconds idle, 3 seconds interval, 3 probes to detect silent network failures.
A quiet CAN bus alone does not trigger reconnects.

Connection states (disconnected, connecting, connected, reconnecting, error) are
separate from telemetry freshness. Stale data still expires by the local monotonic
clock. Diagnostics show endpoint, transport, channel, frame count/rate, last frame
timestamp, retry count, transport/protocol errors, decoder errors and UI drops.
Frames retain identifier, extended flag, DLC, payload, order and channel; diagnostic
records additionally identify transport and gateway. Remote timestamps are gateway
kernel receive wall-clock timestamps, in microseconds. Local SocketCAN timestamps
may have finer precision. Neither timestamp is an end-to-end latency measurement;
use NTP if comparing machines. Error frames and RTR/FD are outside NMEA 2000:
upstream does not forward RTR in this RAW implementation; this adapter accepts
classical data frames only and diagnoses other records.

## Gateway installation (Raspberry Pi OS / Debian Linux)

Run these commands on the gateway from the repository root. Package availability
varies by distribution; the source installation below does not assume an apt
socketcand package exists. These source-build commands require Internet access.

```sh
sudo apt-get update
sudo apt-get install -y git gcc meson ninja-build python3-venv can-utils iproute2
# Build the version inspected in the spike, without remote bus-configuration support.
git clone https://github.com/linux-can/socketcand.git /tmp/socketcand
cd /tmp/socketcand
git checkout 6dd5d33d4645ab221e8cd265c08607366e21ddf1
meson setup build --prefix=/usr/local --buildtype=release -Dlibconfig=false -Dlibsocketcan=false -Dc_args=-DDEBUG
meson compile -C build
sudo meson install -C build
```

Back in the simulator repository:

```sh
python3 -m venv env
env/bin/pip install -e '.[test]'
sudo scripts/setup_vcan.sh
# eth0 is the Ethernet interface, not a hostname or IP. Adjust if renamed.
/usr/local/sbin/socketcand -i vcan0 -l eth0 -p 29536 -n
```

Run in the foreground, or create a systemd service with the same ExecStart and
`KillMode=control-group` (the default). Stop the whole service during restart tests:
terminating only the parent listener can leave existing client processes alive.
No beacon is needed because clients use an explicit endpoint. Configure physical
can0 and its hardware/bitrate separately, then use `-i can0` and dashboard
`--channel can0` for passive reception. Do not expose both buses unnecessarily.

## Security and receive-only limitations

The dashboard sends only protocol bus selection and RAW-mode handshake commands;
it exposes no CAN-send path and does not change interface settings. Socketcand
itself accepts write commands from other clients. The inspected version has no
per-client receive-only ACL, authentication, TLS, or authorization. Compiling without
libsocketcan removes interface-configuration support, not CAN transmission support.
A network allowlist is not CAN write protection against an allowed machine.

Bind only the trusted Ethernet interface, expose only the required CAN interface,
and firewall TCP 29536 to the dashboard addresses. For an existing UFW firewall,
example rules for clients 192.168.50.20 and .21 are:

```sh
sudo ufw insert 1 allow in on eth0 from 192.168.50.20 to any port 29536 proto tcp
sudo ufw insert 2 allow in on eth0 from 192.168.50.21 to any port 29536 proto tcp
sudo ufw insert 3 deny in on eth0 to any port 29536 proto tcp
sudo ufw status numbered
```

Integrate these with your active firewall and verify a disallowed host cannot
connect. Do not enable or reset a firewall remotely without preserving SSH access.
Never expose this service to the Internet or an untrusted LAN. For physical CAN,
use hardware listen-only enforcement if writes must be impossible. Neither this
client nor socketcand bridges vcan0 to can0. Simulator physical-TX safeguards remain
unchanged. Raspberry Pi performance, physical CAN hardware, firewall effectiveness
on your network, and two-machine interoperability remain deployment checks.

## Exact two-machine acceptance procedure

Use the same repository revision on both machines. Example addresses below are
gateway `192.168.50.10`, dashboard `192.168.50.20`. Adjust them to your trusted LAN.
After installation/firewall setup above, run on gateway terminal 1:

```sh
/usr/local/sbin/socketcand -i vcan0 -l eth0 -p 29536 -n
```

Gateway terminal 2 (repository root):

```sh
env/bin/python -m nmea_sim.simulator --channel vcan0 --source-address 233 --unique-number 233
```

Gateway terminal 3 provides independent native decoding for comparison:

```sh
env/bin/python -m nmea_sim.receiver --channel vcan0
```

On the dashboard machine with a desktop session, from the repository root:

```sh
python3 -m venv env
env/bin/pip install -e '.[dashboard,test]'
env/bin/python -m nmea_sim.dashboard --transport socketcand --host 192.168.50.10 --port 29536 --channel vcan0 --source-address 233 --snapshot /tmp/client1.json
```

In another terminal on that machine, start the second independent client:

```sh
env/bin/python -m nmea_sim.dashboard --transport socketcand --host 192.168.50.10 --port 29536 --channel vcan0 --source-address 233 --snapshot /tmp/client2.json
```

Open Diagnostics in both clients. Confirm connected state, increasing frames,
PGNs 127488 and 127489, zero malformed/reassembly errors, and decoded instrument
values matching the gateway receiver for the same payload. Stop the foreground
gateway with Ctrl-C (its terminal process group includes children), leave it down
for five seconds, then rerun the identical command. Both dashboards must show
reconnecting and missing/stale telemetry, then connected and fresh values. Close
the dashboards to write the JSON snapshots. Record both machine versions, addresses,
logs and results before marking physical Ethernet acceptance complete.

## Automated reproduction

On a Linux development host with vcan0 and the gateway binary installed:

```sh
sudo scripts/setup_vcan.sh
env/bin/pip install -e '.[dashboard,test]'
SOCKETCAND=/usr/local/sbin/socketcand env/bin/pytest -q
```

The real-daemon test allocates a loopback TCP port and uses two dashboard backends, a local
SocketCAN backend and the existing simulator. It compares both PGNs against an
independent local decoder, kills the entire gateway process group, checks stale
telemetry and reconnects both clients after restart. It skips when vcan0 or
socketcand is unavailable. TCP protocol fixture tests need loopback socket permission.
Existing local integration tests and decoder tests remain in the full suite.

## Development validation result

Final command executed on the development Linux host:

```sh
SOCKETCAND=/tmp/nmea-socketcand-build/socketcand env/bin/pytest -q
```

Result: **421 passed in 23.81 seconds**, including the real gateway integration
and existing local vcan/Qt regressions; no tests skipped. `git diff --check` passed.
The test daemon was compiled from the pinned upstream source using GCC with
`-DDEBUG` (to enable the upstream listener's address-reuse branch), no libconfig
and no libsocketcan. No installed project dependencies changed. Meson installation
on Raspberry Pi and the two-machine procedure above have not been executed here.
DNS shutdown bounds, physical can0 reception, physical Ethernet, target firewall
rules, and Raspberry Pi load/performance remain unverified deployment assumptions.

Changed files for M6:
- `src/nmea_sim/receive_transport.py`: receive abstraction, local adapter, TCP protocol.
- `src/nmea_sim/dashboard_config.py`: CLI/environment configuration and validation.
- `src/nmea_sim/dashboard_receiver.py`: transport integration, retries and diagnostics.
- `src/nmea_sim/dashboard_backend.py`: configuration forwarding and diagnostic metadata.
- `src/nmea_sim/qml/Main.qml`: connection and transport diagnostic display.
- `tests/test_socketcand.py`: configuration and actual-protocol TCP fixture tests.
- `tests/test_socketcand_integration.py`: real daemon, simulator, clients and restart.
- `tests/test_dashboard_qt.py`: adapter regression, bounded backlog and shutdown tests.
- `.env.example`, `README.md`, `docs/dashboard.md`, `docs/ETHERNET.md`: settings and docs.

The existing plan-file relocation/deletion in the working tree was left untouched.
