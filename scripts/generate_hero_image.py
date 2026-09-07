"""One-off generative-art script for the project's README hero image /
GitHub social preview. Not part of the package -- run once, output
committed as a static PNG under docs/images/.

Concept: a dark "digital primordial soup" -- a scatter of small dim
cells (the vast, mostly-unique population) with a handful of glowing
colored clusters (emergent self-replicators), using the exact palette
the live dashboard uses for highlighted genome clusters, so the hero
image is visually on-brand with the actual tool rather than generic
stock-style abstract art.

Uses macOS's bundled San Francisco variable font directly by path
(/System/Library/Fonts/SFNS.ttf); on another OS, swap in any installed
font supporting Bold/Regular weights.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

rng = np.random.default_rng(7)

SCALE = 2  # supersample for crisp anti-aliasing, then downsample
W, H = 1280 * SCALE, 640 * SCALE

# Same qualitative palette app/streamlit_app.py uses for highlighted
# (repeated-genome) clusters in the population grid.
HIGHLIGHT_RGB = [
    (230, 25, 75), (60, 180, 75), (255, 195, 0), (0, 130, 200),
    (245, 130, 48), (145, 30, 180), (70, 200, 200), (240, 50, 230),
]

BG_TOP = np.array([6, 9, 18])
BG_BOTTOM = np.array([13, 22, 38])
DIM_CELL = (58, 72, 96)


def radial_vignette_background() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    t = yy / H
    base = BG_TOP[None, None, :] * (1 - t[..., None]) + BG_BOTTOM[None, None, :] * t[..., None]
    cy, cx = H * 0.42, W * 0.5
    dist = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 1.3) ** 2)
    dist /= dist.max()
    glow = np.clip(1.0 - dist, 0, 1) ** 2.2
    soup_tint = np.array([22, 38, 46])
    img = base + soup_tint[None, None, :] * glow[..., None] * 0.9
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img, mode="RGB")


def make_cluster_centers(n: int) -> list[tuple[float, float, int]]:
    # Keep clusters clear of the title/subtitle band (bottom ~40%) so the
    # text stays legible on its own. Slot-based placement (a coarse grid,
    # jittered) guarantees spacing in O(n) instead of open-ended rejection
    # sampling, which can stall indefinitely if the safe band is narrow
    # relative to the desired minimum separation.
    cols, rows = 3, 2
    assert cols * rows >= n
    band_x0, band_x1 = 0.08 * W, 0.96 * W
    band_y0, band_y1 = 0.22 * H, 0.62 * H
    slot_w = (band_x1 - band_x0) / cols
    slot_h = (band_y1 - band_y0) / rows
    slots = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(slots)
    centers = []
    for i, (r, c) in enumerate(slots[:n]):
        cx = band_x0 + (c + 0.5) * slot_w + rng.uniform(-0.18, 0.18) * slot_w
        cy = band_y0 + (r + 0.5) * slot_h + rng.uniform(-0.18, 0.18) * slot_h
        centers.append((cx, cy, i))
    return centers


def main() -> None:
    bg = radial_vignette_background()
    cell_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_cells = ImageDraw.Draw(cell_layer)
    draw_glow = ImageDraw.Draw(glow_layer)

    # Background "soup": a scattered field of small unique-genome cells,
    # jittered off a coarse grid so it reads as suspended particles
    # rather than a literal screenshot of the dashboard's pixel grid.
    cell = 15 * SCALE
    for gy in range(0, H, cell):
        for gx in range(0, W, cell):
            if rng.random() < 0.22:
                continue
            jx = gx + rng.uniform(-0.3, 0.3) * cell
            jy = gy + rng.uniform(-0.3, 0.3) * cell
            size = rng.uniform(0.28, 0.42) * cell
            shade = rng.integers(-14, 18)
            color = tuple(int(np.clip(c + shade, 0, 255)) for c in DIM_CELL)
            alpha = int(rng.uniform(70, 150))
            draw_cells.rectangle(
                [jx, jy, jx + size, jy + size], fill=(*color, alpha)
            )

    clusters = make_cluster_centers(6)
    for n_i, (cx, cy, idx) in enumerate(clusters):
        color = HIGHLIGHT_RGB[idx % len(HIGHLIGHT_RGB)]
        n_cells = int(rng.integers(12, 30))
        radius = rng.uniform(0.032, 0.058) * W
        for _ in range(n_cells):
            ang = rng.uniform(0, 2 * np.pi)
            r = radius * np.sqrt(rng.random())
            px = cx + r * np.cos(ang)
            py = cy + r * np.sin(ang) * 0.85
            size = rng.uniform(0.4, 0.62) * cell
            draw_cells.rectangle(
                [px, py, px + size, py + size], fill=(*color, 235)
            )
        # Soft glow blob behind the cluster (additive bloom).
        glow_alpha = int(rng.uniform(55, 85))
        draw_glow.ellipse(
            [cx - radius * 1.7, cy - radius * 1.7, cx + radius * 1.7, cy + radius * 1.7],
            fill=(*color, glow_alpha),
        )

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=22 * SCALE / 2))

    composite = bg.convert("RGBA")
    composite = Image.alpha_composite(composite, glow_layer)
    composite = Image.alpha_composite(composite, cell_layer)

    # Extra fine grain glow pass so the brightest cluster cores bloom.
    bright_only = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_bright = ImageDraw.Draw(bright_only)
    for cx, cy, idx in clusters:
        color = HIGHLIGHT_RGB[idx % len(HIGHLIGHT_RGB)]
        draw_bright.ellipse(
            [cx - 10 * SCALE, cy - 10 * SCALE, cx + 10 * SCALE, cy + 10 * SCALE],
            fill=(*color, 160),
        )
    bright_only = bright_only.filter(ImageFilter.GaussianBlur(radius=9 * SCALE))
    composite = Image.alpha_composite(composite, bright_only)

    draw = ImageDraw.Draw(composite)

    def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f

    title = "COMPUTATIONAL LIFE LAB"
    title_font = font("Bold", 66 * SCALE)
    subtitle = "A digital primordial soup for emergent self-replication"
    subtitle_font = font("Regular", 26 * SCALE)

    margin_x = 72 * SCALE
    baseline_y = H * 0.72

    def tracked_text(draw_obj, xy, text, fnt, fill, tracking=0):
        x, y = xy
        for ch in text:
            draw_obj.text((x, y), ch, font=fnt, fill=fill)
            w = draw_obj.textlength(ch, font=fnt)
            x += w + tracking

    tracked_text(draw, (margin_x, baseline_y), title, title_font, (255, 255, 255, 255), tracking=4 * SCALE)

    accent_y = baseline_y + 66 * SCALE * 1.05
    draw.rectangle(
        [margin_x + 3, accent_y, margin_x + 3 + 90 * SCALE, accent_y + 5 * SCALE],
        fill=(70, 200, 200, 255),
    )

    draw.text(
        (margin_x, accent_y + 24 * SCALE),
        subtitle,
        font=subtitle_font,
        fill=(198, 208, 222, 255),
    )

    final = composite.convert("RGB").resize((1280, 640), Image.LANCZOS)
    out_path = Path(__file__).resolve().parents[1] / "docs" / "images" / "hero.png"
    final.save(out_path, optimize=True)
    print("saved", out_path, final.size)


if __name__ == "__main__":
    main()
