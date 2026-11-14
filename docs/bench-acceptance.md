# Physical bench acceptance record — NOT EXECUTED

This is a blank evidence record, not an approval. Follow hardware-transition.md.
Do not mark a row PASS from software mocks, vcan captures or a read-only
preflight report. Do not use an operational vessel bus or a live engine.

| Item | Actual observation / evidence | Status |
| --- | --- | --- |
| Operator and test date | Pending | NOT RUN |
| HAT model | User reports Waveshare 2-CH CAN HAT (Isolated) | NOT INSPECTED |
| HAT revision / photographed jumpers | Pending | NOT RUN |
| Host | User reports Raspberry Pi 3; exact variant pending | NOT INSPECTED |
| OS, kernel, Python, python-can versions | Pending | NOT RUN |
| SPI/interrupt/16 MHz oscillator verified | Pending | NOT RUN |
| Physical connector to Linux interface mapping | Pending | NOT RUN |
| Isolation from vessel and engine | Pending physical verification | NOT RUN |
| Power source, fuse rating, current limit | Pending device/cable-specific settings | NOT RUN |
| Measured backbone voltage/current | Pending | NOT RUN |
| Two end terminators / powered-off H–L resistance | Pending; expected about 60 ohms total | NOT RUN |
| H/L/reference/shield pinout and isolation verified | Pending | NOT RUN |
| Assigned manufacturer identity evidence | Default 2046 is unassigned and physical-TX blocked | BLOCKED |
| Unique number, device/system/engine instances, preferred source | Pending reserved values | NOT RUN |
| Read-only preflight JSON | Pending can0 report | NOT RUN |
| Operator explicitly approves physical TX | No approval recorded | NOT RUN |
| 250 kbit/s, UP, normal mode, controller state | Pending actual ip output | NOT RUN |
| External ACK-capable peer and physical RX confirmed | Pending controller/display capture | NOT RUN |
| Controller error counters before/after | Pending; investigate increases/bus-off | NOT RUN |
| NAME stable across restart; no duplicate identity | Pending | NOT RUN |
| Discovery requests / responses / PGN lists | Pending raw capture and independent decode | NOT RUN |
| Engine fields, units, unavailable values, cadence | Pending raw capture and field-level report | NOT RUN |
| Controlled simulated-node collision behavior | Pending approved bench test | NOT RUN |
| Shutdown / transmitter stopped | Pending observed receiver/display behavior | NOT RUN |
| Garmin model and firmware | Pending | NOT RUN |
| Garmin discovery, engine instance and supported gauges | Pending photographs/capture and field results | NOT RUN |
| Garmin unsupported fields distinguished from failures | Pending | NOT RUN |
| Licensed-standard / conformance gap review | Group functions and other limitations in protocol-matrix.md | OPEN |
| Reviewer / final physical disposition | Pending evidence review | OPEN |

Attach actual artifacts under a distinct dated capture directory. Preserve raw
frames, decoder/tool versions, SHA-256 values, wiring photos and device lists.
Any failed electrical/identity/controller gate stops the session. Supplying an
assigned identity and TX flag does not by itself approve or certify this setup.
