"""Converts Intercom's snapshot pictures (.ppm) to .png, with the standard
library only (no ImageMagick needed).

    python3 ppm_to_png.py <file.ppm>... --out <folder> [--crop WxH+X+Y]

INTERCOM_SNAPSHOT=<folder> makes Intercom save its screens as .ppm (see the
README, Part 3). --crop keeps only part of each picture, like ImageMagick's
-crop: width x height + left + top.
"""

import argparse
import struct
import zlib
from pathlib import Path


def read_ppm(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    # Header: "P6", width, height, max value, each followed by whitespace.
    fields, pos = [], 0
    while len(fields) < 4:
        while data[pos : pos + 1].isspace():
            pos += 1
        start = pos
        while not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    if fields[0] != b"P6" or fields[3] != b"255":
        raise ValueError(f"{path}: not an 8-bit P6 picture")
    width, height = int(fields[1]), int(fields[2])
    return width, height, data[pos + 1 : pos + 1 + width * height * 3]


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    row = width * 3
    raw = b"".join(b"\x00" + rgb[y * row : (y + 1) * row] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def crop(width: int, height: int, rgb: bytes, spec: str) -> tuple[int, int, bytes]:
    size, x, y = spec.split("+")
    w, h = (int(v) for v in size.split("x"))
    x, y = int(x), int(y)
    w, h = min(w, width - x), min(h, height - y)
    rows = (rgb[((y + r) * width + x) * 3 : ((y + r) * width + x + w) * 3] for r in range(h))
    return w, h, b"".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--crop")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.files:
        width, height, rgb = read_ppm(path)
        if args.crop:
            width, height, rgb = crop(width, height, rgb, args.crop)
        target = args.out / (path.stem + ".png")
        write_png(target, width, height, rgb)
        print(target)


if __name__ == "__main__":
    main()
