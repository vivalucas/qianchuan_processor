from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
ICO_PATH = ASSETS_DIR / "app.ico"
ICNS_PATH = ASSETS_DIR / "app.icns"
PNG_PATH = ASSETS_DIR / "app-icon-1024.png"


def rounded_rectangle_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def lerp(a, b, t):
    return int(a + (b - a) * t)


def gradient_background(size):
    top = (16, 182, 167)
    mid = (17, 106, 141)
    bottom = (24, 50, 79)
    img = Image.new("RGBA", (size, size))
    pix = img.load()
    for y in range(size):
        t = y / (size - 1)
        if t < 0.54:
            local = t / 0.54
            color = tuple(lerp(top[i], mid[i], local) for i in range(3))
        else:
            local = (t - 0.54) / 0.46
            color = tuple(lerp(mid[i], bottom[i], local) for i in range(3))
        for x in range(size):
            side_light = int(10 * (1 - abs((x / size) - 0.28)))
            pix[x, y] = tuple(min(255, c + side_light) for c in color) + (255,)
    mask = rounded_rectangle_mask(size, int(size * 0.21))
    img.putalpha(mask)
    return img


def draw_icon(size):
    img = gradient_background(size)
    draw = ImageDraw.Draw(img, "RGBA")
    scale = size / 1024

    def box(values):
        return tuple(int(v * scale) for v in values)

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")
    sd.rounded_rectangle(box((268, 232, 756, 792)), radius=int(88 * scale), fill=(8, 32, 50, 84))
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(24 * scale)))
    img.alpha_composite(shadow)

    draw.rounded_rectangle(box((304, 272, 720, 752)), radius=int(64 * scale), fill=(232, 255, 251, 255))
    draw.rounded_rectangle(box((354, 340, 670, 684)), radius=int(24 * scale), fill=(18, 52, 80, 255))

    arrow = [box((566, 390)), box((444, 512)), box((566, 634)), box((608, 592)), box((558, 542)), box((704, 542)), box((704, 482)), box((558, 482)), box((608, 432))]
    draw.polygon(arrow, fill=(81, 234, 216, 255))

    draw.rounded_rectangle(box((404, 700, 620, 728)), radius=int(14 * scale), fill=(18, 52, 80, 72))
    draw.ellipse(box((494, 218, 530, 254)), fill=(215, 247, 242, 220))
    return img


def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    base = draw_icon(1024)
    base.save(PNG_PATH)
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(ICO_PATH, sizes=ico_sizes)
    try:
        base.save(ICNS_PATH, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    except Exception as exc:
        raise RuntimeError(f"Failed to write macOS .icns icon: {exc}") from exc


if __name__ == "__main__":
    main()
