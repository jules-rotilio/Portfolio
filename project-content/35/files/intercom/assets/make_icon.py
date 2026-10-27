"""Draws Intercom's icon: a wall intercom (speaker grille and call button) with
sound waves, in the app's amber on its dark panel color.

Writes icon.png (512 px, built into the program), the sizes Linux desktops
use (icons/<n>.png), and icon.ico for Windows. Run from anywhere:
    python3 assets/make_icon.py
Needs Pillow. Drawn at 2048 px and scaled down, so the edges are smooth.
"""
import math
import pathlib
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent
BIG = 2048
S = BIG / 512  # the shapes below are given on a 512 px grid

AMBER = (0xF5, 0xA5, 0x24, 255)
INK = (0x1A, 0x13, 0x00, 255)          # text on amber, in the app
TOP, BOTTOM = (0x2A, 0x2F, 0x38), (0x12, 0x14, 0x18)


def box(x0, y0, x1, y1):
    return [x0 * S, y0 * S, x1 * S, y1 * S]


def draw():
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    # The tile: a vertical gradient, cut to a rounded square.
    gradient = Image.new("RGBA", (BIG, BIG))
    g = ImageDraw.Draw(gradient)
    for y in range(BIG):
        t = y / (BIG - 1)
        g.line([(0, y), (BIG, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    mask = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(16, 16, 496, 496), radius=108 * S, fill=255)
    img.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # The intercom unit.
    d.rounded_rectangle(box(84, 92, 300, 420), radius=44 * S, fill=AMBER)
    for y in (142, 186, 230, 274):                     # speaker grille slots
        d.rounded_rectangle(box(126, y, 258, y + 20), radius=10 * S, fill=INK)
    d.ellipse(box(160, 322, 224, 386), fill=INK)        # call button
    d.ellipse(box(176, 338, 208, 370), fill=AMBER)
    # Sound waves: 30 px strokes centered on radius r (PIL paints a thick
    # arc inward from its box, hence the r + 15), with round ends.
    for r in (64, 120):
        cx, cy = 318, 256
        o = r + 15
        d.arc(box(cx - o, cy - o, cx + o, cy + o), start=-42, end=42, fill=AMBER, width=int(30 * S))
        for a in (-42, 42):
            x = cx + r * math.cos(math.radians(a))
            y = cy + r * math.sin(math.radians(a))
            d.ellipse(box(x - 15, y - 15, x + 15, y + 15), fill=AMBER)
    return img


def main():
    img = draw()
    img.resize((512, 512), Image.LANCZOS).save(HERE / "icon.png")
    (HERE / "icons").mkdir(exist_ok=True)
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        img.resize((n, n), Image.LANCZOS).save(HERE / "icons" / f"{n}.png")
    img.resize((256, 256), Image.LANCZOS).save(
        HERE / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == "__main__":
    main()
