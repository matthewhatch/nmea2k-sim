"""Convenience launcher; reads SocketCAN directly through the dashboard package."""
from nmea_sim.dashboard import main

if __name__ == '__main__':
    raise SystemExit(main())
