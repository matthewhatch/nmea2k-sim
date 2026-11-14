"""Read classic extended-frame candump -L captures for offline diagnostics/tests."""
import re
from pathlib import Path
from typing import Iterator
import can


def read_candump(path: Path) -> Iterator[can.Message]:
    for number, line in enumerate(path.read_text().splitlines(), 1):
        match = re.fullmatch(r'\(([0-9.]+)\) \S+ ([0-9A-Fa-f]{8})#([0-9A-Fa-f]*)', line)
        if not match:
            raise ValueError(f'unsupported candump line {number}')
        timestamp, identifier, payload = match.groups()
        yield can.Message(timestamp=float(timestamp), arbitration_id=int(identifier, 16),
                          data=bytes.fromhex(payload), is_extended_id=True, check=True)
