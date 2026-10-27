"""Records a few seconds from a microphone and tells what its "silence" is
made of: real noise, or a constant offset (DC) that only looks like noise.

    python3 mic_check.py [source] [seconds]

`source` is a PulseAudio/PipeWire source name (list them with
`pactl list short sources`); without it, the default mic. Stay quiet while
it records. Linux only (it uses `parec`); standard library otherwise.

This is how the -17 dB of the AMD laptop's digital mic turned out to be an
offset (+0.26 on one side), which Intercom now removes (see gate.rs).
"""

import math
import struct
import subprocess
import sys


def db(v: float) -> float:
    return 20 * math.log10(max(v, 1e-9))


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else None
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    cmd = ["parec", "--rate=48000", "--channels=2", "--format=float32le", "--raw"]
    if source:
        cmd.append(f"--device={source}")
    # parec runs until stopped: read exactly `seconds` of sound, then stop it.
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as parec:
        raw = parec.stdout.read(int(seconds * 48000) * 8)
        parec.terminate()
    n = len(raw) // 8 * 2
    samples = struct.unpack(f"<{n}f", raw[: n * 4])
    samples = samples[len(samples) // 4 :]  # the first moments can hold a click
    if not samples:
        sys.exit("nothing recorded: is the source name right?")

    left, right = samples[0::2], samples[1::2]
    mono = [(l + r) / 2 for l, r in zip(left, right)]
    print(f"{len(mono) / 48000:.1f} s recorded from {source or 'the default mic'}\n")
    print(f"{'':6}{'offset':>16}{'peak':>10}{'noise (rms)':>14}")
    for name, side in (("left", left), ("right", right), ("mono", mono)):
        mean = sum(side) / len(side)
        peak = max(abs(v) for v in side)
        noise = math.sqrt(sum((v - mean) ** 2 for v in side) / len(side))
        print(f"{name:6}{mean:+8.4f} ({db(abs(mean)):5.1f} dB){db(peak):7.1f} dB{db(noise):11.1f} dB")
    mean = sum(mono) / len(mono)
    peak = max(abs(v) for v in mono)
    print()
    if abs(mean) > 0.01 and db(abs(mean)) > db(peak) - 6:
        print("The level you see in silence is mostly a constant offset, not sound.")
        print("Intercom removes it before its meter and its noise gate.")
    else:
        print("No real offset: this is the mic's own noise. The noise gate handles it.")


if __name__ == "__main__":
    main()
