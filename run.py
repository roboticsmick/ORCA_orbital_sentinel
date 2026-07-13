#!/usr/bin/env python3
"""!
@file run.py
@brief Convenience launcher for ORCA Orbital Sentinel.
@details
    Thin wrapper so the app can be started without module syntax.

    Example:
        python run.py
        ORCA_OFFLINE=1 python run.py
"""
import sys
from orca_orbital_sentinel.app import main

if __name__ == "__main__":
    sys.exit(main())
