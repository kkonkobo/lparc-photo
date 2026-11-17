"""Draw the app icon and the small UI glyphs. Run: uv run python packaging/make_assets.py"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "src" / "lparc_photo" / "assets"
SS = 4  # supersampling for smooth edges


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        draw.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return img


def icon(size: int = 1024) -> Image.Image:
    s = size * SS
    # macOS icon grid: artwork inset ~10 %, corner radius ~22.5 % of the artwork.
    inset, radius = int(s * 0.1), int(s * 0.8 * 0.225)
    mask = Image.new("L", (s, s))
    ImageDraw.Draw(mask).rounded_rectangle([inset, inset, s - inset, s - inset], radius, fill=255)
    art = vertical_gradient(s, (90, 150, 255), (40, 82, 200))
    out = Image.new("RGBA", (s, s))
    out.paste(art, mask=mask)

    d = ImageDraw.Draw(out)
    white = (255, 255, 255, 255)
    # viewfinder corners
    m, L, w = int(s * 0.25), int(s * 0.12), int(s * 0.035)
    for x0, y0, dx, dy in ((m, m, 1, 1), (s - m, m, -1, 1), (m, s - m, 1, -1), (s - m, s - m, -1, -1)):
        d.rounded_rectangle(sorted_box(x0, y0, x0 + dx * L, y0 + dy * w), w // 2, fill=white)
        d.rounded_rectangle(sorted_box(x0, y0, x0 + dx * w, y0 + dy * L), w // 2, fill=white)
    # portrait: head and shoulders, clipped to the frame
    cx = s // 2
    head_r = int(s * 0.095)
    head_cy = int(s * 0.44)
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=white)
    body = Image.new("L", (s, s))
    ImageDraw.Draw(body).ellipse([cx - int(s * 0.19), int(s * 0.57), cx + int(s * 0.19), int(s * 0.9)], fill=255)
    clip = Image.new("L", (s, s))
    ImageDraw.Draw(clip).rectangle([0, 0, s, int(s * 0.7)], fill=255)
    out.paste(white, mask=ImageChops.darker(body, clip))
    return out.resize((size, size), Image.Resampling.LANCZOS)


def sorted_box(x0, y0, x1, y1):
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def glyph(points: list[tuple[float, float]], size: int = 32, width: float = 3.2) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s))
    ImageDraw.Draw(img).line([(x * s, y * s) for x, y in points], fill=(255, 255, 255, 255), width=int(width * SS), joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    app_icon = icon()
    app_icon.save(ASSETS / "icon.png")
    # Windows installer icon; PyInstaller converts the PNG for the app itself.
    app_icon.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    glyph([(0.22, 0.52), (0.42, 0.72), (0.78, 0.3)]).save(ASSETS / "check.png")
    glyph([(0.28, 0.4), (0.5, 0.62), (0.72, 0.4)], width=2.6).save(ASSETS / "chevron.png")
    glyph([(0.28, 0.6), (0.5, 0.38), (0.72, 0.6)], width=2.6).save(ASSETS / "chevron-up.png")
    print("wrote", *sorted(p.name for p in ASSETS.iterdir()))


if __name__ == "__main__":
    main()
