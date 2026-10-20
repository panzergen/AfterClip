"""Generate packaging/afterclip.ico from a simple vector-ish drawing.

Kept in the repo so the icon can be regenerated (and tweaked) rather than
being an opaque binary blob:

    python packaging/make_icon.py

Requires Pillow, which is only needed at authoring time -- the icon itself is
a committed .ico file.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "afterclip.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)

BG_TOP = (37, 99, 235)  # blue-600
BG_BOTTOM = (29, 78, 216)  # blue-700
PLAY = (255, 255, 255)
CLIP = (191, 219, 254)


def draw_icon(size: int) -> Image.Image:
    """Render one square icon at the given size."""
    scale = 4  # draw big, downsample for clean edges
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded square background with a vertical gradient.
    gradient = Image.new("RGBA", (1, s))
    for y in range(s):
        t = y / max(1, s - 1)
        gradient.putpixel(
            (0, y),
            (
                round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
                round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
                round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t),
                255,
            ),
        )
    gradient = gradient.resize((s, s))

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    image.paste(gradient, (0, 0), mask)

    # Film-strip sprocket holes down the left edge.
    hole_w = int(s * 0.055)
    hole_h = int(s * 0.075)
    hole_x = int(s * 0.115)
    gap = int(s * 0.115)
    y = int(s * 0.18)
    while y + hole_h < s * 0.86:
        draw.rounded_rectangle(
            [hole_x, y, hole_x + hole_w, y + hole_h], radius=max(1, hole_w // 3), fill=CLIP
        )
        y += hole_h + gap

    # A play triangle, centred in the remaining space.
    cx = int(s * 0.63)
    cy = s // 2
    half = int(s * 0.20)
    draw.polygon(
        [(cx - int(half * 0.75), cy - half), (cx - int(half * 0.75), cy + half), (cx + half, cy)],
        fill=PLAY,
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    # PIL downsamples a single large master into every requested size, which
    # gives cleaner edges than pre-rendering each size separately.
    master = draw_icon(max(SIZES))
    master.save(OUT, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
