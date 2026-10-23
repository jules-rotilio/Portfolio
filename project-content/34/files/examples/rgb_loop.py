#!/usr/bin/env python3
"""Cycle the mouse light through all colours (Ctrl+C to stop).

Uses the light preview command, which changes the colour live without saving it
to the mouse's memory, so it can run forever without wearing the flash. When it
stops, the saved light setting is shown again.

Usage: rgb_loop.py [SECONDS_PER_CYCLE] [--for SECONDS]
"""
import colorsys
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from valkyrie import device, model  # noqa: E402


def main():
    args = sys.argv[1:]
    duration = None
    if '--for' in args:
        i = args.index('--for')
        duration = float(args[i + 1])
        del args[i:i + 2]
    period = float(args[0]) if args else 5.0

    mouse = device.open_mouse()
    with mouse.session():
        n = mouse.read_active()
        saved = model.decode_light(mouse.read(device.light_addr(n), 6))

    start = time.monotonic()
    try:
        while duration is None or time.monotonic() - start < duration:
            hue = (time.monotonic() - start) / period % 1.0
            r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0))
            mouse.preview_light(model.Light((r, g, b), brightness=3, breathing=0))
    except KeyboardInterrupt:
        pass
    finally:
        mouse.preview_light(saved)


if __name__ == '__main__':
    main()
