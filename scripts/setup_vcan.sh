#!/bin/sh
set -eu
# Creates only virtual vcan0. Invoke with sudo.
modprobe vcan
if ! ip link show dev vcan0 >/dev/null 2>&1; then
    ip link add dev vcan0 type vcan
fi
# Refuse to alter an existing interface of a different type.
ip -details link show dev vcan0 | grep -q 'vcan ' || {
    echo 'vcan0 exists but is not a virtual CAN interface' >&2
    exit 1
}
ip link set dev vcan0 up
ip -details link show dev vcan0
