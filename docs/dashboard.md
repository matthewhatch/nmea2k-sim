# M5 — native NMEA 2000 engine instruments

A PySide6 / Qt Quick desktop application. It is an independent, receive-only
SocketCAN client using the same decoders as the console consumer. It imports no
engine model or simulator state and uses no web, messaging or network service.

## Install and run

Linux, Python 3.11+, SocketCAN and a working X11 or Wayland desktop are required.
Install the optional GUI extra; base simulator/consumer installations do not
require Qt:

```sh
env/bin/python -m pip install -e '.[test,dashboard]'
```

For Debian-family X11 desktops, Qt also requires system XCB libraries. On this
host all were present except the cursor library:

```sh
sudo apt-get install libxcb-cursor0
```

Other distributions may use different package names. See the official
[Qt Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html). The app
reports a missing desktop session or cursor library before Qt attempts to start.
It does not download/install libraries or configure CAN interfaces at runtime.

After the usual `sudo scripts/setup_vcan.sh`, run in separate terminals:

```sh
# Independent receiver / native instruments
python dashboard.py --channel vcan0
# Equivalent installed entrypoints:
env/bin/python -m nmea_sim.dashboard --channel vcan0
# or: env/bin/nmea-dashboard --channel vcan0
```

```sh
# Separate simulator process; choose a unique number for each simulated node
env/bin/python -m nmea_sim.simulator --channel vcan0 --unique-number 1
```

Changing the dashboard to `--channel can0` requires no application edits or TX
opt-in. Its connection never transmits requests, claims or engine commands.
Controller bitrate, modes and physical setup remain external; consult the bench
guide. A receive-only Python application does not itself configure a hardware
controller to listen-only. The simulator's physical TX and manufacturer guards
are unchanged.

## Configuration and selection

Channel precedence is CLI `--channel` > `NMEA_CAN_CHANNEL` > `vcan0`, sharing
interface-name validation with the existing entrypoints.

| Option | Behavior |
| --- | --- |
| --stale-after SECONDS | Per-PGN monotonic freshness timeout; default 3 seconds |
| --source-address N | Initial engine selection by source, not a transmit address |
| --engine-instance N | Initial engine selection by decoded instance |
| --quit-after SECONDS | Optional bounded demonstration |
| --snapshot FILE | One diagnostic JSON snapshot at exit, only when requested |
| --screenshot FILE | One PNG at bounded demo completion; requires --quit-after |

The engine selector lists each `(CAN source, engine instance)` independently.
Without initial selection options the first observed engine is selected. An
operator can select another engine/source in the UI. Source reassignment creates
a new entry; select it explicitly. A known different NAME at the same source
clears that source's old sensor values, preventing cross-device mixing.
Selection is not based on files or simulator internals.

## Instruments and status

The tachometer and temperature gauge animate between decoded updates. Digital
values show voltage (V), oil pressure (bar), fuel (L/h), hours (h) and trim (%).
Temperature converts decoded Kelvin to Celsius; pressure converts Pa to bar.
Presentation rounds values, while the diagnostic panel retains decoded precision.
Needles clamp to the visual scale (0–7000 RPM and 0–120 C); numeric readings
still show the received value beyond that scale.

An unavailable value displays `--`; valid zero remains zero. With no engine data
the application waits with empty instruments. Rapid and dynamic PGNs have
separate freshness timers: fresh RPM does not keep an old temperature/voltage
reading alive. Old values and status indicators become unavailable independently.
Losing both PGNs shows communication loss. Interface errors hide readings
immediately and leave the UI responsive with an actionable error and Reconnect.
Reconnect clears previous-session readings and diagnostics before receiving again.

Running/stopped uses only fresh decoded RPM (>0 / zero); missing or stale RPM
means Unknown. High temperature, low oil pressure and low voltage indicators
use the corresponding NMEA 2000 status bits, not measurement thresholds.
Warnings include all named decoded status flags. Grey status indicators mean
unknown/stale; Clear means the fresh corresponding reported flag is clear.
No arbitrary threshold alarms or engine commands are implemented.

## Diagnostics

Open Diagnostics to inspect the newest 200 received frames, including unknown or
ignored traffic. Rows show extended identifier, PGN/source when applicable,
SocketCAN Unix timestamp, raw frame bytes, decoded fields for completed packets,
and decode errors. Fast-packet intermediate rows have no fabricated decoded
telemetry. Standard/remote/error/FD frames cannot update the instruments.

PGN/source filters take decimal values; blank means all. Pause view freezes the
visible trace for scrolling/filtering while CAN decoding and instruments keep
updating. Resume returns to the live trace. There is no persistent history store.

Counters distinguish raw frames, complete decoded messages, malformed PGN
payloads and fast-packet reassembly events. Fast-packet counters include invalid
lengths, orphan/reordered/duplicate fragments, timeouts and capacity eviction;
their sum is not a distinct-packet-loss count. Receive rate is a one-second raw
frame window. Bounded signal batches and diagnostic buffers prevent CAN traffic
from blocking rendering; UI-drop counts disclose discarded display events under
heavy load. Data whose update was dropped eventually becomes stale rather than
being invented.

## Architecture

- `transport.py`: shared SocketCAN opener; dashboard always uses transmit=False.
- `receiver.py` / `fast_packet.py`: existing protocol decoding and bounded reassembly; added observable error counters without changing payload layouts.
- `dashboard_receiver.py`: one CAN QThread, 50 ms receive timeout, batched Qt signals and bounded GUI backpressure; no UI rendering or simulator imports.
- `telemetry.py`: Qt-independent state keyed by source/instance, per-PGN freshness, unit presentation and protocol-reported status.
- `dashboard_backend.py`: main-thread selection, diagnostic filters, counters and Qt property notifications.
- `qml/`: Qt Quick instruments and diagnostic presentation, with no PGN parsing.
- `dashboard.py`: native launcher, lifecycle and optional one-time test artifacts.

The receive thread owns its CAN socket and decoder. GUI state lives on the main
thread. Closing/Ctrl-C requests interruption, closes the socket and joins the
worker. No competing CAN reader runs in UI callbacks. PySide6 is pinned to 6.8.3;
its [QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html) signals and
[QML application engine](https://doc.qt.io/qtforpython-6/PySide6/QtQml/QQmlApplicationEngine.html)
provide the native event/rendering separation.

## Tests and reproduction

```sh
env/bin/python -m pytest -q -rs
```

Qt tests use the offscreen software renderer and verify loaded QML gauge values,
smooth numeric targets, fast packets, missing data, status bits, freshness,
selection, diagnostic filters/pause, malformed frames and graceful failures.
Real-vcan tests run the dashboard and simulator as separate processes, save
actual screenshots/snapshots, verify fresh decoded values, then verify selected
engine communication loss after its simulator stops. Other engine traffic does
not keep that selection fresh. Live tests skip with a reason when vcan0 is
unavailable; GUI tests skip if the optional PySide6 extra is absent.

To reproduce a live capture (reserve source/unique number 237):

```sh
env/bin/python scripts/capture_dashboard.py --output-dir /tmp/dashboard-demo
```

This renders native Qt offscreen while receiving real vcan0 frames from a
separate simulator. It creates one PNG and one diagnostic snapshot. With an X11
desktop available use `--platform xcb`; in CI it can run under Xvfb. Screenshot
artifacts under `docs/captures/m5-dashboard-live.*` were recorded with the actual
X11/xcb backend in Xvfb, software rendering and live CAN data.

The development host lacked libxcb-cursor0 and sudo package installation required
an unavailable password. X11 verification used a downloaded distribution package
unpacked under `/tmp` and a process-local LD_LIBRARY_PATH; no system installation
or runtime workaround was added to the application. Normal X11 users should
install the system dependency above. Offscreen Qt tests need no X11 cursor library.

## Troubleshooting / deployment limits

- Cannot connect to display: launch from a desktop session. Headless verification can use `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software` with --quit-after.
- xcb plugin/library error: install Qt's Linux system dependencies and inspect `QT_DEBUG_PLUGINS=1` output. This host specifically needs libxcb-cursor0.
- Missing CAN interface: set up vcan0 separately or choose the configured physical interface. The dashboard never creates or changes links.
- Socket opens but no engine data: verify interface UP, external bitrate/mode, source/instance selection and raw traffic with candump; a bound socket does not prove physical bus health.
- Engine values disappear: inspect separate PGN freshness and diagnostic counters. Silence means Unknown/communication loss, not a stopped engine measurement.
- Blank/dark window: restart the updated launcher, which now defaults to the verified software renderer. To override an existing shell setting, use `QT_QUICK_BACKEND=software env/bin/python dashboard.py --channel vcan0`. Instruments render even without a simulator; only readings need CAN traffic. An explicit QT_QUICK_BACKEND override is respected. GPU/Pi performance remains unverified.

On the user's Pi 3, use a supported 64-bit OS/Python/PySide6 distribution or a
compatible native build. Wheel/ABI availability must be checked for that image;
the x86-64 build and Xvfb tests do not establish ARM deployment or performance.
Physical CAN and Garmin acceptance remain the open M4 bench gates. No proprietary
protocol, remote control, network service or historical telemetry database was added.


## Verification recorded on 2026-11-13

**396 tests passed in 21.53s, no skips**, including real vcan0 dashboard and
simulator processes, stale-state handling and all preceding protocol tests.
Native X11/xcb launch was also verified separately in Xvfb. The committed live
screenshot/snapshot show source 237, engine instance 1, 2961 RPM and 25.71 C;
`m5-dashboard-live.validation.json` records Qt version, method and artifact hashes.
The screenshot was captured from actual CAN-fed instruments, not seeded UI data.
M4 physical/Pi/Garmin gates remain open.
