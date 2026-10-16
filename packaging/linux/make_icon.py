"""Draw the Lumen icon (the in-app Logo: an orange tile with three bars) as PNG files.

    python make_icon.py OUT_DIR [SIZE ...]     # writes OUT_DIR/lumen-<SIZE>.png
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (0xF0, 0xA5, 0x3A, 255)  # C.accent
INK = (0x1A, 0x12, 0x04, 255)     # C.onAccent


def icon(size: int) -> Image.Image:
    scale = 4  # draw large, then downsample for smooth edges
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s / 4, fill=ACCENT)
    pad = s * 0.26
    inner = s - 2 * pad
    bar = s * 2 / 28  # 2 px bars on the 28 px logo
    gap = (inner - 3 * bar) / 4  # spaceEvenly
    for i, width in enumerate((0.6, 1.0, 0.75)):
        y = pad + gap * (i + 1) + bar * i
        d.rounded_rectangle((pad, y, pad + inner * width, y + bar), radius=bar / 2, fill=INK)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for size in [int(a) for a in sys.argv[2:]] or [256, 512]:
        icon(size).save(out / f"lumen-{size}.png")
