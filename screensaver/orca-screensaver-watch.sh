#!/usr/bin/env bash
# Idle watcher: locks the GNOME session and shows the ORCA Orbital Sentinel
# globe fullscreen a few seconds before the desktop's own idle timer would
# blank the screen. GNOME's own lock/auth is untouched - this only decides
# *when* to lock and what to show while locked. Dismissed by any key press
# or mouse movement (handled inside orca_orbital_sentinel's --screensaver
# mode), which reveals the real GNOME unlock prompt underneath.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python3"

# Trigger a few seconds before `gsettings get org.gnome.desktop.session idle-delay`
# (in ms). Override with ORCA_IDLE_MS if you change that setting.
THRESHOLD_MS="${ORCA_IDLE_MS:-880000}"
POLL_S=5

while true; do
    idle_ms=$(xprintidle)
    if [ "$idle_ms" -ge "$THRESHOLD_MS" ]; then
        loginctl lock-session
        "$PYTHON" "$PROJECT_DIR/run.py" --screensaver || true
        sleep 2   # let the desktop settle before resuming idle polling
    fi
    sleep "$POLL_S"
done
