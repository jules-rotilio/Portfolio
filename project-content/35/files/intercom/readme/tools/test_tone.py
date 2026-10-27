"""Endless music-like test sound on stdout, for trying "Capture program audio"
without a real music player.

    python3 test_tone.py | pacat --playback --rate=48000 --channels=2 \\
        --format=s16le --client-name="Music Player"

Add --device=<sink> to pacat to play into a speaker nobody hears, e.g. one made with
    pactl load-module module-null-sink sink_name=silent
In Intercom, the program shows up as "Music Player" (its key is "pacat").
Format: 48 kHz, stereo, 16-bit little-endian. Standard library only.
"""

import math
import struct
import sys

RATE = 48000
# A slow arpeggio, a quarter of a second per note.
NOTES = [262, 330, 392, 523, 392, 330]


def main() -> None:
    out = sys.stdout.buffer
    t = 0
    try:
        while True:
            block = bytearray()
            for _ in range(RATE // 10):
                seconds = t / RATE
                pitch = NOTES[int(seconds * 4) % len(NOTES)]
                envelope = 1.0 - (seconds * 4) % 1.0
                s = int(0.35 * envelope * math.sin(2 * math.pi * pitch * seconds) * 32767)
                block += struct.pack("<hh", s, s)
                t += 1
            out.write(block)
            out.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
