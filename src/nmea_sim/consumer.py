"""Receive-only NMEA 2000 console diagnostics; receiver remains an alias."""
from .receiver import Decoder, main

__all__ = ['Decoder', 'main']

if __name__ == '__main__':
    raise SystemExit(main())
