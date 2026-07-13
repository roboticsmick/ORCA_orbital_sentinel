"""!
@file __init__.py
@brief Package marker and public entry point for ORCA Orbital Sentinel.
@details Exposes run() so `python -m orca_orbital_sentinel` and
    `from orca_orbital_sentinel import run` both work.
"""

from .app import run, main

__all__ = ["run", "main"]
__version__ = "0.1.0"
