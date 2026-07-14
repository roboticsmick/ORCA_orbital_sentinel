"""!
@file simulate.py
@brief Watch the round-display firmware run live, in a window, with no hardware.
@details
    Compiles the firmware's real render.cpp and sgp4.cpp into a host binary that streams
    RGB565 frames, and blits them into a pygame window at the panel's true 240x240 with
    the round bezel drawn on. What you see is what the panel draws: same SGP4 positions,
    same projection, same palette, same 16-bit quantisation.

    Works on Windows, macOS and Linux.

    Usage:
        python tools/preview/simulate.py
        python tools/preview/simulate.py --theme cyberpunk --scale 3
        python tools/preview/simulate.py --accel 90        # fast-forward the orbits

    Keys:  Esc / Q  quit        S  save a PNG of the current frame

    Requires pygame (`pip install pygame` or, on Python 3.13+, `pip install pygame-ce`)
    and a C++ compiler - or none at all, if you `pip install ziglang`.

    Note: there is no Wi-Fi here, so this propagates the element sets baked into
    tle_fallback.h rather than fetching fresh ones. Station phase drifts from reality as
    those elements age; the geometry, colours and timing are exactly the panel's.
"""

import argparse
import os
import subprocess
import sys

import numpy as np
import pygame

from build_preview import BUILD, SKETCH, THEMES, find_compiler

HERE = os.path.dirname(os.path.abspath(__file__))

PANEL_W = 240
PANEL_H = 240
FRAME_BYTES = PANEL_W * PANEL_H * 2

SOURCES = [
    os.path.join(HERE, "simulate_main.cpp"),
    os.path.join(SKETCH, "render.cpp"),
    os.path.join(SKETCH, "sgp4.cpp"),
]


def build(theme):
    """! @brief Compile the simulator for a theme. @return Path to the executable."""
    cxx = find_compiler()
    if cxx is None:
        sys.exit("No C++ compiler found. Install one, or: pip install ziglang")

    os.makedirs(BUILD, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    exe = os.path.join(BUILD, "simulate_{0}{1}".format(theme, suffix))
    cmd = (cxx + ["-std=c++17", "-O2", "-w",
                  "-DORCA_THEME={0}".format(THEMES[theme]),
                  "-I", SKETCH, "-I", HERE]
           + SOURCES + ["-o", exe])

    print("compiling ({0})...".format(theme))
    subprocess.run(cmd, check=True)
    return exe


def read_frame(pipe):
    """! @brief Read exactly one full frame, or None if the stream ended.
    @details A pipe read can return short, so loop until the frame is whole - otherwise
             the image tears and every later frame is offset by the shortfall.
    """
    buf = bytearray()
    while len(buf) < FRAME_BYTES:
        chunk = pipe.read(FRAME_BYTES - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def rgb565_to_surface(raw):
    """! @brief Expand a raw RGB565 frame into a pygame Surface.
    @details pygame cannot take RGB565 directly (frombuffer only speaks 8-bit-per-channel
             formats), so widen it here. The high bits are replicated into the low ones,
             which is what the panel does optically - so the window matches the hardware
             rather than looking artificially darker.
    """
    px = np.frombuffer(raw, dtype="<u2").reshape(PANEL_H, PANEL_W)
    r = (px >> 11) & 0x1F
    g = (px >> 5) & 0x3F
    b = px & 0x1F
    rgb = np.dstack((
        (r << 3) | (r >> 2),
        (g << 2) | (g >> 4),
        (b << 3) | (b >> 2),
    )).astype(np.uint8)
    return pygame.image.frombuffer(rgb.tobytes(), (PANEL_W, PANEL_H), "RGB")


def main():
    ap = argparse.ArgumentParser(description="Live round-display simulator.")
    ap.add_argument("--theme", choices=sorted(THEMES), default="retro")
    ap.add_argument("--scale", type=int, default=2,
                    help="integer upscale; 2 => a 480x480 window")
    ap.add_argument("--tz-offset", type=float, default=10.0,
                    help="hours to add to UTC for the clock (Brisbane = 10)")
    ap.add_argument("--accel", type=float, default=None,
                    help="simulated seconds per real second; default is config.h's "
                         "TIME_ACCELERATION. Try 90 to watch the stations move.")
    args = ap.parse_args()

    exe = build(args.theme)
    cmd = [exe, str(args.tz_offset)]
    if args.accel is not None:
        cmd.append(str(args.accel))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=0)

    pygame.init()
    size = (PANEL_W * args.scale, PANEL_H * args.scale)
    window = pygame.display.set_mode(size)
    pygame.display.set_caption(
        "ORCA Orbital Sentinel - Round Display ({0})".format(args.theme))
    clock = pygame.time.Clock()
    frame_no = 0

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_s:
                        path = "round_display_frame_{0:04d}.png".format(frame_no)
                        pygame.image.save(window, path)
                        print("saved", path)

            raw = read_frame(proc.stdout)
            if raw is None:
                print("simulator exited")
                break
            frame_no += 1

            # .convert() matches the display's pixel format. Without it the panel is a
            # 24-bit surface and the window is 32-bit, and scaling straight into the
            # window raises "Source and destination surfaces need to be compatible
            # formats". Converting the 240x240 surface is cheap; scaling into the
            # window then avoids a second blit.
            panel = rgb565_to_surface(raw).convert(window)
            pygame.transform.scale(panel, size, window)
            pygame.display.flip()
            clock.tick(60)          # The producer sets the real pace; don't spin here.
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        pygame.quit()


if __name__ == "__main__":
    main()
