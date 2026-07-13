# ORCA Orbital Sentinel

A retro-LCD Earth that traces the continents as dots and shows live satellites
(and the ISS) orbiting in real time, with a NASA/JPL near-Earth-object impact-risk
panel. Built by [ORCA](https://github.com/roboticsmick).

![ORCA Orbital Sentinel preview](assets/orbital_sentinel_preview.png)

This is the Python desktop reference implementation. It is deliberately structured
as a portable **core** (propagation, projection, rasterisation) plus a swappable
**renderer**, so the same logic can later drive a lock-screen screensaver, a
Raspberry Pi framebuffer, or a microcontroller LCD.

## Vision

The end goal is for Orbital Sentinel to run as an actual lock-screen screensaver:

- **Desktop** - Windows, macOS, and Linux lock-screen/screensaver integration.
- **Raspberry Pi** - fullscreen kiosk on a small round or square display.
- **ESP32** - a minimal standalone build on a Wi-Fi-connected round LCD panel
  (e.g. the [Seeed Studio round display](https://wiki.seeedstudio.com/get_start_round_display/)).

None of that is built yet. This repo is currently the desktop reference
implementation only - see [Roadmap](#roadmap).

## Features

- Dotted globe built from real public-domain Natural Earth coastline data (bundled, works offline).
- Live satellite tracking via CelesTrak GP/TLE data, propagated with SGP4.
- Crewed stations (ISS and China's CSS/Tiangong) drawn as labelled crosses, not dots.
- Config-driven filtering: show only what you want (by id, name, altitude band, or count).
- Compact small-screen mode for LCD/OLED panels, defaulting to just the two stations.
- Front/back hemisphere shading and globe occlusion for a genuine 3D read.
- NASA/JPL Sentry near-Earth-object risk panel.
- Retro aesthetic: chunky upscaled pixels, phosphor palette, CRT scanlines.
- Graceful degradation: live -> local cache -> optional TLE file -> synthesized demo.

## Requirements

- Python 3.9+
- Linux desktop (X11 or Wayland). See Troubleshooting for headless notes.

Python packages (see `requirements.txt`): `numpy`, `pygame`, `requests`, `sgp4`.

## Install

```bash
git clone https://github.com/roboticsmick/ORCA_orbital_sentinel.git
cd ORCA_orbital_sentinel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python run.py
# or, equivalently:
python -m orca_orbital_sentinel
```

Offline mode (skip all network; use cache/fallback/synthesized demo):

```bash
ORCA_OFFLINE=1 python run.py
```

Fullscreen (native display resolution, same HUD layout scaled up):

```bash
python run.py --fullscreen
# or: ORCA_FULLSCREEN=1 python run.py
```

## Controls

| Key         | Action            |
| ----------- | ----------------- |
| `Space`     | Pause / resume    |
| `Esc` / `Q` | Quit              |

## Configuration

All knobs live in `orca_orbital_sentinel/config.py`. The ones you are most likely to touch:

- `CELESTRAK_GROUP` - which satellites to track. Default `visual` (~150 bright,
  well-spread objects; polite on bandwidth). Set to `active`, `starlink`,
  `gps-ops`, etc. for a denser swarm.
- `TIME_ACCELERATION` - simulated seconds per real second. Default `60`
  (one ISS orbit every ~90 s). Set to `1` for real-time.
- `SPIN_DEG_PER_SEC` - cosmetic camera spin rate (does not affect physics).
- `GLOBE_RADIUS_FRAC`, `WINDOW_W/H`, `LOGICAL_SCALE` - size and pixel chunkiness.
- Palette colours (`COL_*`) - swap the phosphor green for amber, etc.

## Filtering (limiting what is shown)

Filtering runs once at load, so a tighter filter also means fewer objects to
propagate each frame - a lighter, faster view. Set any of these in
`orca_orbital_sentinel/config.py` (leave as `None` to ignore):

- `FILTER_INCLUDE_IDS` - a set of NORAD ids to show exclusively, e.g. `{25544, 48274}`.
- `FILTER_EXCLUDE_IDS` - ids to drop.
- `FILTER_NAME_CONTAINS` - keep only names containing a substring (e.g. `"STARLINK"`).
- `FILTER_MIN_ALT_KM` / `FILTER_MAX_ALT_KM` - keep only a given altitude band.
- `FILTER_MAX_COUNT` - hard cap after the above.

Stations listed in `STATION_LABELS` are always drawn as labelled crosses when
present. ISS is amber, CSS is orange; add more `id -> label` / `id -> colour`
entries to mark other objects.

## Screensaver / lock screen (Ubuntu, GNOME + X11)

`--screensaver` (or `ORCA_SCREENSAVER=1`) runs fullscreen and exits on the
*first* key press or mouse movement, instead of Space toggling pause. That
makes it a suitable idle-time visual, but it does not authenticate anyone -
GNOME's own lock (your real login password) stays completely in charge of
actually securing the session. The `screensaver/` folder wires the two
together: an idle watcher locks the session and shows the globe fullscreen a
few seconds before GNOME's own idle timer would otherwise blank the screen;
dismissing the globe (any key/mouse input) just reveals GNOME's already-active
unlock prompt underneath.

```bash
sudo apt install xprintidle       # used to detect idle time on X11
```

Install the watcher as a per-user systemd service:

```bash
mkdir -p ~/.config/systemd/user
ln -s /path/to/ORCA_orbital_sentinel/screensaver/orca-screensaver.service \
      ~/.config/systemd/user/orca-screensaver.service
systemctl --user daemon-reload
systemctl --user enable --now orca-screensaver.service
```

Check it's running / see logs:

```bash
systemctl --user status orca-screensaver.service
journalctl --user -u orca-screensaver.service -f
```

By default it triggers 20 s before `gsettings get org.gnome.desktop.session
idle-delay` (880 s vs. the default 900 s / 15 min). Override with
`ORCA_IDLE_MS` (edit the `Environment=` line in the `.service` file, or the
default at the top of `orca-screensaver-watch.sh`) if you change that
GNOME setting. To stop using it:

```bash
systemctl --user disable --now orca-screensaver.service
```

This is X11-only (`xprintidle` reads the XScreenSaver extension's idle
counter); it will not work under a Wayland session.

## Small screens / LCD panels

A compact mode renders at a panel's native resolution (default 240x240, suited to
an ST7789 TFT) and, by default, shows only the two crewed stations.

Preview it on the desktop (upscaled window):

```bash
python run_lcd.py
# or
python -m orca_orbital_sentinel --small
```

Drive a real SPI panel on a Raspberry Pi:

```bash
pip install luma.lcd pillow          # hardware-only extras
ORCA_DISPLAY=spi python run_lcd.py
```

Typical ST7789 wiring (Raspberry Pi 40-pin):

| Panel | Pi pin        |
| ----- | ------------- |
| VCC   | 3V3           |
| GND   | GND           |
| SCL   | SCLK (GPIO11) |
| SDA   | MOSI (GPIO10) |
| RES   | GPIO25        |
| DC    | GPIO24        |
| CS    | CE0 (GPIO8)   |
| BLK   | 3V3           |

Choose what the small screen shows via `SMALL_INCLUDE_IDS`, `SMALL_GROUP`, and the
panel size (`SMALL_W`, `SMALL_H`) in `config.py`. For a monochrome SSD1306 OLED,
set `SMALL_W/H` to `128`/`64`, install `luma.oled`, and point `SpiPanelSink` at the
`ssd1306` device (the sink is a thin, documented adapter in `hardware.py`). The
`DisplaySink` boundary means the renderer itself is unchanged across panels.

## Data sources and rate limits

- **Satellites:** CelesTrak GP data (`https://celestrak.org`). CelesTrak refreshes
  roughly every two hours and firewalls abusive pollers, so this app caches
  downloads and never refetches faster than `TLE_CACHE_TTL_S` (default 3 h). Do not
  lower that without reason.
- **Near-earth objects:** NASA/JPL CNEOS Sentry API
  (`https://ssd-api.jpl.nasa.gov/sentry/`), cached for 24 h. The JPL terms ask for
  one request at a time and no embedding the API in a website; this client honours
  that. API formats can change without notice, so the code checks defensively and
  degrades to sample rows on any failure.

Note: CelesTrak is retiring the legacy 5-digit-catalog TLE text format as the
catalog passes 69999 (mid-2026). The propagator here is format-agnostic, but a
future revision should prefer CelesTrak's OMM (JSON/CSV) output for longevity.

## Offline behaviour

With no network (or `ORCA_OFFLINE=1`) and no cache, the app draws a **synthesized
demo constellation** (SGP4-valid, deterministic) so the globe is never empty. To
pin your own real objects for offline use, drop a standard 3-line TLE file at
`orca_orbital_sentinel/data/fallback_tle.txt`; it is used ahead of the demo.

## Architecture

```text
config.py       tunables, palette, filter + small-screen settings (no logic)
propagate.py    SGP4 + TEME->ECEF + geodetic transforms   <- portable core
camera.py       orthographic projection and occlusion      <- portable core
coastline.py    bundled Natural Earth dots -> ECEF cloud    <- portable core
filters.py      declarative object filter (id/name/alt/count)
tle_source.py   cached CelesTrak fetch + fallback chain     <- data layer
sentry.py       cached JPL Sentry NEO rows                  <- data layer
render.py       desktop pygame renderer (pixels + HUD)      <- renderer
render_small.py compact panel renderer                      <- renderer
hardware.py     display sinks: desktop preview or SPI panel <- output
app.py          desktop simulation loop and wiring
app_small.py    compact/LCD simulation loop and wiring
```

The `propagate`/`camera`/`coastline` trio is intentionally free of any display
dependency: it turns time into an abstract set of screen points. Porting to a new
target (Windows/macOS screensaver window, Pi DRM framebuffer, ESP32 SPI display)
means writing a new renderer against that same point stream, not rewriting the
simulation.

## Repository layout

```text
ORCA_orbital_sentinel/
├── assets/                          preview image(s) for this README
├── orca_orbital_sentinel/           the Python package (see Architecture)
│   └── data/                        bundled coastline + optional offline TLE file
├── screensaver/                     GNOME/X11 idle-watcher systemd unit + script
├── run.py                           desktop launcher
├── run_lcd.py                       small-screen/LCD launcher
└── requirements.txt
```

## Troubleshooting

- **Wayland vs X11:** the app is a normal window and runs on both. (True animated
  *wallpaper* is a separate, harder problem on GNOME/Wayland and is intentionally
  out of scope here.)
- **No display / SSH:** for a headless render, set `SDL_VIDEODRIVER=dummy` and save
  frames with `pygame.image.save`; there is no live window in that mode.
- **`pygame` fails to open a window:** ensure you are in a graphical session and
  that SDL can reach your display server.
- **`pip install` reports dependency conflicts for unrelated packages** (e.g.
  `openhsi-ros2 requires netcdf4, which is not installed`): harmless. It means a
  ROS environment (or similar) is sourced in your shell and its `PYTHONPATH`
  leaks into the venv, so pip's resolver notices those unrelated packages too.
  It does not affect this project - `numpy`/`pygame`/`requests`/`sgp4` still
  install into and load from `.venv`. To silence it, unset `PYTHONPATH` before
  creating the venv: `unset PYTHONPATH && python3 -m venv .venv`.

## Roadmap

- Native lock-screen/screensaver integration for Windows and macOS.
- XScreenSaver hook (`-window-id`) as the Linux screensaver renderer.
- Raspberry Pi fullscreen kiosk build (round/square display).
- Standalone ESP32 build on a Wi-Fi-connected round LCD panel.
- OMM (JSON) ingestion to survive the 6-digit catalog transition.
- Optional GLSL post-process (bloom, barrel distortion) on the upscale.
- Extraction of the core into a C ABI shared library with pybind11 bindings, for
  a native microcontroller (ESP32/RP2040) build.

Done: station cross-markers, object filtering, and a compact LCD/OLED mode with a
swappable display sink (desktop preview and SPI panel).

## Licensing / attribution

Coastline geometry derives from Natural Earth (public domain). Orbital data from
CelesTrak and NASA/JPL CNEOS are subject to their respective terms; review them
before redistributing cached data.
