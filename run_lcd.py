#!/usr/bin/env python3
"""!
@file run_lcd.py
@brief Launcher for the compact small-screen (LCD/OLED) station view.
@details
    Convenience wrapper equivalent to `python -m orca_orbital_sentinel --small`.

    Example:
        python run_lcd.py                          # desktop preview window
        ORCA_DISPLAY=spi python run_lcd.py         # push to a wired SPI panel
        ORCA_OFFLINE=1 python run_lcd.py           # no network (demo/cache)
"""
import os
import sys

from orca_orbital_sentinel.app_small import run_small

if __name__ == "__main__":
    _allow = os.environ.get("ORCA_OFFLINE", "0") != "1"
    sys.exit(run_small(allow_network=_allow))
