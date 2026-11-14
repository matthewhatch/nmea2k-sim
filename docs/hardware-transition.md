# M4 hardware transition: Waveshare 2-CH CAN HAT (Isolated), Raspberry Pi 3

Status: virtual interoperability and software gates verified; physical bench and
Garmin acceptance **NOT RUN**. The user identified the original isolated 2-CH
CAN HAT and RPi 3. Board revision, jumpers, installed OS/kernel and physical
wiring must still be inspected. No physical interface was configured or used.

The current default manufacturer 2046 is explicitly unassigned, vcan-only and
blocked on physical interfaces even with TX opt-in. A physical bench session
requires an operator-owned assigned identity and a separate explicit approval.
There is no automatic hardware setup script.

## References and board identification

Checked on 2026-11-13:

- [Waveshare original 2-CH CAN HAT product](https://www.waveshare.com/product/iot-communication/wired-comm-converter/2-ch-can-hat.htm) and [wiki](https://www.waveshare.com/wiki/2-CH_CAN_HAT): MCP2515 classic CAN, isolated interface, selectable logic level and termination. This guide targets the original 2-CH CAN HAT, not HAT+ or CAN FD models.
- [Waveshare schematic](https://files.waveshare.com/upload/1/15/2-CH-CAN-HAT-Schematic.pdf): 16 MHz crystals, SPI chip selects, selectable interrupt routing, isolated SGND and termination circuitry. Check the actual revision against it.
- [Raspberry Pi overlay reference](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/README): MCP2515 overlay parameters use BCM GPIO numbers. [Boot configuration documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html) identifies the active config.txt location.
- [iproute2 CAN JSON implementation](https://github.com/iproute2/iproute2/blob/main/ip/iplink_can.c): mode flags are omitted when zero; preflight accounts for that format.
- [Linux SocketCAN documentation](https://www.kernel.org/doc/html/latest/networking/can.html): bitrate, controller modes, counters and local echo.
- [Garmin termination troubleshooting](https://support.garmin.com/en-HK/?faq=656KiuIo733b27xQgmLBy7): an unpowered correctly terminated backbone measures approximately 60 ohms between data lines.
- [NMEA identity information](https://www.nmea.org/nmea-2000.html): manufacturer assignment/certification are not provided by these software tests.

## Electrical bench checklist

Use a dedicated bench backbone, physically disconnected from every operational
vessel bus and live engine. Take photographs and record the checks in the
[acceptance record](bench-acceptance.md).

1. Power down before mounting the HAT or changing jumpers. Set host logic VIO for the Pi's 3.3 V signals. Confirm each selected SPI chip-select and interrupt jumper matches the overlay. Check for GPIO conflicts with other hardware.
2. Use a current-limited, appropriately fused supply through a proper NMEA 2000 power tee and correctly rated backbone/drop cables. Set voltage and fuse rating from the connected devices/cable documentation. A nominal 12 V backbone supply must **never** feed a Pi 5 V/3.3 V pin or a CAN data terminal. Power the Pi by its proper supply.
3. Connect CAN_H to backbone NET-H and CAN_L to NET-L. Verify connector orientation and continuity from the actual cable/board pinout; do not rely on wire color alone. Connect the bus reference to the HAT's isolated-side SGND as required by its schematic. Preserve isolation from Pi-side ground; do not bridge it inadvertently with a USB instrument or cable shield.
4. Fit exactly two 120-ohm terminators at the physical ends of the backbone. Count any enabled HAT termination jumper as a terminator. Disable it for a mid-backbone drop when the two end terminators already exist. With all power removed, verify about 60 ohms between H and L before powering the bus.
5. Add a second active CAN controller or suitable bench display for ACK and reception. A second Python consumer on the same can0 socket interface is not a second controller and does not provide an external ACK. CAN1 on the HAT can be a second controller in a separately reviewed bench setup; verify both channels and reference wiring. Do not assume that the two channels are isolated from each other simply because they are isolated from the Pi.
6. Record bus voltage, current, termination, isolation checks and device list. Stop for unexpected current, rising errors, bus-off, a duplicate NAME, or any connection to a vessel network.

```text
120-ohm end -- backbone tees / fused power tee -- 120-ohm end
                    |                 |
             HAT CAN channel     independent ACK/receive peer
             isolated H/L/SGND   (bench controller or display)
```

## Pi driver setup (for a later approved bench session)

Install Python 3.11+, the package, iproute2 and can-utils on the Pi. Record OS,
kernel, Python and python-can versions. Existing virtual test results were
obtained on the development host; they do not prove the Pi build or hardware.

Back up and edit the active boot configuration. Modern Raspberry Pi OS uses
`/boot/firmware/config.txt`; older images may use `/boot/config.txt`. Verify the
installed image rather than editing both. The following is a **conditional
one-channel example**, not a statement of the current jumper positions:

```ini
# Only if the board's selected controller is wired to SPI0 CE0,
# its interrupt is actually BCM25, and its crystal is 16 MHz:
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
```

For a second controller use the installed overlay reference for SPI0 CE1 and
its actual interrupt routing; do not copy the first controller's interrupt.
Overlay names do not establish which physical terminal became Linux can0 or
can1. After a controlled reboot with the bench disconnected, inspect:

```sh
uname -a
python3 --version
ip -details link show
journalctl -k -b
```

Resolve driver errors, incorrect clocks, GPIO conflicts and channel mapping
before wiring an energized bench. MCP2515 is classic CAN; CAN FD is not used.
Internal controller loopback and SocketCAN local echo are different mechanisms;
neither substitutes for checking electrical isolation before a loopback test.

## 250 kbit/s configuration (documented, not executed)

Only after the bench checks and explicit operator authorization, identify the
intended channel. These commands change can0 and therefore are not run by any
application or test in this repository:

```sh
sudo ip link set dev can0 down
sudo ip link set dev can0 type can bitrate 250000 listen-only off loopback off restart-ms 0
sudo ip link set dev can0 up
ip -details -statistics link show dev can0
```

Expect kernel type can, bitrate 250000, UP, normal controller mode and
ERROR-ACTIVE. Bus-off/passive/error growth requires investigation before TX,
not repeated blind restarts. A listen-only sniffer cannot acknowledge frames.
For a receive-only hardware observation phase, configure controller listen-only
externally if required by the bench procedure; the Python consumer does not
set hardware modes.

Read-only software inspection is available without opening a CAN socket:

```sh
env/bin/python -m nmea_sim.preflight --channel can0
```

It reports interface type, UP, bitrate, controller state/modes, identity and
opt-in checks. Default 2046/absent physical opt-in intentionally fail on can0.
It never changes a link or transmits. The report always says
`transmission_authorized: false`; even all software checks passing cannot
verify wiring, manufacturer assignment, isolation or operator authorization.
iproute2 omits ctrlmode when there are no active mode flags; explicit unknown
mode formats or active incompatible modes fail inspection.

## Configuration-only application transition

No Python source edits are needed. After all gates pass, supply the actual
assigned manufacturer value (not a copied example identity), reserve a unique
number and source address, and run the same simulator with `--channel can0`,
`--manufacturer-code ASSIGNED_VALUE`, `--unique-number UNIQUE_VALUE`, and
`--allow-physical-tx`. The placeholders must be replaced with documented values.
The consumer changes only to `--channel can0` and needs no TX opt-in.

The transport guard still blocks a physical interface renamed vcan0. Assigned
identity without opt-in is also blocked. Unit tests use mocked physical metadata
to prove these code paths; no such test transmits on hardware. Product metadata
and certification remain unavailable unless genuinely supported; supplying an
assigned manufacturer alone does not make this a certified device.

## Physical and Garmin acceptance

Save pre/post controller statistics, a candump -L capture, independent field-level
decode, identity/request responses and source-conflict observations. Verify an
external controller actually received frames; local echo alone is insufficient.
Record timing, engine instance, units, unavailable values, and stable NAME after
restart. Exercise conflicts only between controlled simulated bench devices.

A Garmin test requires its exact model/firmware, supported engine fields, a
separate isolated display setup and actual observed results. Check discovery,
engine instance mapping, displayed RPM/trim/dynamic units and behavior when TX
stops. Record absent/unsupported fields separately from failures. No Garmin
compatibility is inferred from vcan or CANboat results. Complete the acceptance
record before marking M4 physical acceptance passed.
