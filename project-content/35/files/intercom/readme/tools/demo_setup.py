"""Writes a demo Intercom setup into a folder, for screenshots that never show
your own sounds or settings.

    python3 demo_setup.py <folder>

Creates:
  <folder>/config/intercom/config.toml   a page of demo sounds
  <folder>/config/discord/               so Settings › Audio shows the Discord tips
  <folder>/sounds/*.wav                  the demo sounds (synthesized tones)

Then run Intercom with XDG_CONFIG_HOME=<folder>/config (Linux) to use it.
Only the Python standard library is needed.
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 22050

# Key name in config.toml -> (sound name, seconds, base pitch in Hz).
# Num5 is long: the screenshot script plays it, and "Now playing" shows its progress.
SOUNDS = {
    "Num1": ("Airhorn", 1.5, 440),
    "Num2": ("Drumroll", 2.0, 110),
    "Num3": ("Applause", 2.5, 220),
    "Num4": ("Rimshot", 0.6, 330),
    "Num5": ("Victory fanfare", 20.0, 262),
    "Num6": ("Sad trombone", 2.0, 196),
    "Num7": ("Laugh track", 2.0, 294),
    "Num8": ("Boo", 1.5, 147),
    "Num9": ("Wow", 1.0, 523),
    "NumPlus": ("Air raid siren", 4.0, 350),
    "NumMinus": ("Record scratch", 0.8, 180),
}


def tone(seconds: float, pitch: float) -> bytes:
    """A little arpeggio around `pitch`, so the meters move."""
    frames = bytearray()
    notes = [1.0, 1.25, 1.5, 2.0]
    for i in range(int(seconds * RATE)):
        t = i / RATE
        note = notes[int(t * 4) % len(notes)]
        envelope = 1.0 - (t * 4) % 1.0
        s = 0.4 * envelope * math.sin(2 * math.pi * pitch * note * t)
        frames += struct.pack("<h", int(s * 32767))
    return bytes(frames)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    sounds = root / "sounds"
    config = root / "config" / "intercom"
    sounds.mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)
    (root / "config" / "discord").mkdir(parents=True, exist_ok=True)

    toml = ['[voice]', 'effect = "robot"', "", "[[page]]", 'name = "Demo sounds"', ""]
    for key, (name, seconds, pitch) in SOUNDS.items():
        path = sounds / f"{name}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(tone(seconds, pitch))
        toml += [f"[page.keys.{key}]", f'files = ["{path}"]', "volume = 1.0", ""]
    toml += ["[[page]]", 'name = "Memes"', ""]
    (config / "config.toml").write_text("\n".join(toml))
    print(f"demo setup in {root}")


if __name__ == "__main__":
    main()
