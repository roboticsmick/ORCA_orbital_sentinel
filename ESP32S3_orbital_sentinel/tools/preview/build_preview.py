"""!
@file build_preview.py
@brief Compile the firmware's renderer for the host and save PNGs of the panel.
@details
    Builds preview_main.cpp against the sketch's *real* render.cpp and sgp4.cpp, so
    the PNGs are a faithful simulation of the Round Display - not an illustration.
    Every pixel has already been through the same RGB565 quantisation the panel
    applies, and the round bezel mask is the renderer's own.

    Needs a C++ compiler. Any of these will do, tried in order:
      - $CXX
      - g++ / clang++ on PATH
      - `python -m ziglang c++` (pip install ziglang) - no toolchain setup needed

    Usage:
        python tools/preview/build_preview.py
        python tools/preview/build_preview.py --frames 4 --step 900 --scale 2

    Options:
        --time   ISO UTC instant of the first frame (default: a nice ISS pass).
        --frames Number of frames to render.
        --step   Simulated seconds between frames.
        --scale  Integer upscale for the PNG (nearest-neighbour, keeps it crisp).
        --out    Output path (single frame) or directory prefix (multiple).
"""

import argparse
import os
import shutil
import subprocess
import sys

# Pillow is imported lazily, inside the functions that write PNGs. simulate.py reuses
# this module's build helpers but renders to a window instead of a file, so it must not
# be forced to install Pillow just to import us.

HERE = os.path.dirname(os.path.abspath(__file__))
SKETCH = os.path.normpath(os.path.join(HERE, "..", "..", "orbital_sentinel"))
BUILD = os.path.join(HERE, "build")

PANEL_W = 240
PANEL_H = 240

SOURCES = [
    os.path.join(HERE, "preview_main.cpp"),
    os.path.join(SKETCH, "render.cpp"),
    os.path.join(SKETCH, "sgp4.cpp"),
]


def find_compiler():
    """! @brief Return an argv prefix that invokes a C++ compiler, or None."""
    env = os.environ.get("CXX")
    if env:
        return [env]
    for exe in ("g++", "clang++"):
        path = shutil.which(exe)
        if path:
            return [path]
    # ziglang ships a complete clang toolchain as a pip wheel - no system compiler.
    try:
        subprocess.run([sys.executable, "-m", "ziglang", "version"],
                       capture_output=True, check=True)
        return [sys.executable, "-m", "ziglang", "c++"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


THEMES = {"retro": 0, "cyberpunk": 1}


def build(theme="retro"):
    """! @brief Compile the preview binary for a theme.
        @param theme "retro" or "cyberpunk".
        @return Path to the executable.
    @details The firmware selects its palette at compile time (#if ORCA_THEME), so the
             theme is a -D define here rather than a runtime flag. Each theme gets its
             own binary so switching back and forth does not force a rebuild.
    """
    cxx = find_compiler()
    if cxx is None:
        sys.exit("No C++ compiler found. Install one, or: pip install ziglang")

    os.makedirs(BUILD, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    exe = os.path.join(BUILD, "preview_{0}{1}".format(theme, suffix))
    cmd = (cxx + ["-std=c++17", "-O2", "-w",
                  "-DORCA_THEME={0}".format(THEMES[theme]),
                  "-I", SKETCH, "-I", HERE]
           + SOURCES + ["-o", exe])

    print("compiling ({0}):".format(theme),
          " ".join(os.path.basename(s) for s in SOURCES))
    subprocess.run(cmd, check=True)
    return exe


def rgb565_to_rgb888(buf):
    """! @brief Expand raw little-endian RGB565 to 8-bit RGB.
        @details Replicates the high bits into the low ones, which is what the
                 panel does optically - so the PNG matches what the eye sees.
    """
    out = bytearray(PANEL_W * PANEL_H * 3)
    for i in range(PANEL_W * PANEL_H):
        v = buf[2 * i] | (buf[2 * i + 1] << 8)
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        out[3 * i] = (r << 3) | (r >> 2)
        out[3 * i + 1] = (g << 2) | (g >> 4)
        out[3 * i + 2] = (b << 3) | (b >> 2)
    return bytes(out)


def circular_alpha(img):
    """! @brief Punch out the invisible corners so the PNG reads as a round panel."""
    from PIL import Image, ImageDraw

    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, img.size[0] - 1, img.size[1] - 1), fill=255)
    img.putalpha(mask)
    return img


def main():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("This script writes PNGs and needs Pillow:  pip install pillow\n"
                 "(For the live simulator, which needs no Pillow, run simulate.py.)")

    ap = argparse.ArgumentParser()
    # Defaults compose a frame with both stations and the home marker in view.
    ap.add_argument("--time", default="2026-07-13T05:32:47")
    ap.add_argument("--frames", type=int, default=1)
    ap.add_argument("--step", type=float, default=120.0)
    ap.add_argument("--azimuth", type=float, default=300.0,
                    help="camera spin in degrees; any value is a real moment")
    ap.add_argument("--tz-offset", type=float, default=10.0,
                    help="hours to add to UTC for the on-screen clock (Brisbane=10)")
    ap.add_argument("--theme", choices=sorted(THEMES), default="retro",
                    help="palette: retro (phosphor green) or cyberpunk (neon-noir)")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    exe = build(args.theme)
    proc = subprocess.run(
        [exe, args.time, str(args.frames), str(args.step), str(args.azimuth),
         str(args.tz_offset)],
        capture_output=True, check=True)
    sys.stderr.write(proc.stderr.decode(errors="replace"))

    frame_bytes = PANEL_W * PANEL_H * 2
    raw = proc.stdout
    got = len(raw) // frame_bytes
    if got != args.frames:
        sys.exit(f"expected {args.frames} frames, got {got}")

    default_out = os.path.normpath(
        os.path.join(HERE, "..", "..", "..", "assets", "round_display_preview.png"))
    out = args.out or default_out
    os.makedirs(os.path.dirname(out), exist_ok=True)

    paths = []
    for f in range(args.frames):
        chunk = raw[f * frame_bytes:(f + 1) * frame_bytes]
        img = Image.frombytes("RGB", (PANEL_W, PANEL_H),
                              rgb565_to_rgb888(chunk))
        if args.scale > 1:
            img = img.resize((PANEL_W * args.scale, PANEL_H * args.scale),
                             Image.NEAREST)
        img = circular_alpha(img)

        if args.frames == 1:
            path = out
        else:
            stem, ext = os.path.splitext(out)
            path = f"{stem}_{f:02d}{ext}"
        img.save(path)
        paths.append(path)

    for p in paths:
        print("wrote", p)


if __name__ == "__main__":
    main()
