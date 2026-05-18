#!/usr/bin/env python3
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]

IOS_ICON = ROOT / "ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png"
IOS_SPLASH_DIR = ROOT / "ios/App/App/Assets.xcassets/Splash.imageset"
ANDROID_RES = ROOT / "android/app/src/main/res"
MAC_BUILD_DIR = ROOT / "build"
MAC_ICONSET_DIR = MAC_BUILD_DIR / "icon.iconset"
MAC_ICON_ICNS = MAC_BUILD_DIR / "icon.icns"
MAC_ICON_PNG = MAC_BUILD_DIR / "icon.png"

BG_TOP = (8, 16, 29)
BG_BOTTOM = (10, 39, 79)
ACCENT = (120, 230, 255)
ACCENT_STRONG = (83, 185, 255)
WARM = (255, 176, 125)
WHITE = (246, 251, 255)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def gradient(size):
    image = Image.new("RGBA", (size, size))
    px = image.load()
    for y in range(size):
      t = y / max(size - 1, 1)
      row = tuple(lerp(BG_TOP[i], BG_BOTTOM[i], t) for i in range(3)) + (255,)
      for x in range(size):
        px[x, y] = row
    return image


def add_radial_glow(image, center, radius, color, alpha):
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
    return Image.alpha_composite(image, glow)


def load_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def add_grid(draw, size):
    spacing = max(size // 10, 24)
    for x in range(0, size + 1, spacing):
        draw.line((x, 0, x, size), fill=(255, 255, 255, 18), width=max(size // 512, 1))
    for y in range(0, size + 1, spacing):
        draw.line((0, y, size, y), fill=(255, 255, 255, 18), width=max(size // 512, 1))


def draw_wordmark(image, text, y_ratio=0.58, scale=0.34):
    draw = ImageDraw.Draw(image)
    font = load_font(int(image.size[0] * scale), bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (image.size[0] - width) / 2
    y = image.size[1] * y_ratio - height / 2
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.text((x, y + image.size[0] * 0.012), text, font=font, fill=(*ACCENT, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(image.size[0] // 50, 6)))
    image.alpha_composite(shadow)
    draw.text((x, y), text, font=font, fill=WHITE)


def draw_chart_mark(image, inset_ratio=0.17):
    draw = ImageDraw.Draw(image)
    size = image.size[0]
    inset = int(size * inset_ratio)
    line = [
        (inset, int(size * 0.64)),
        (int(size * 0.35), int(size * 0.5)),
        (int(size * 0.5), int(size * 0.58)),
        (int(size * 0.68), int(size * 0.34)),
        (size - inset, int(size * 0.28)),
    ]

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for point in line:
        odraw.ellipse(
            (
                point[0] - size * 0.035,
                point[1] - size * 0.035,
                point[0] + size * 0.035,
                point[1] + size * 0.035,
            ),
            fill=(*ACCENT, 110),
        )
    odraw.line(line, fill=(*ACCENT_STRONG, 180), width=max(size // 18, 8), joint="curve")
    overlay = overlay.filter(ImageFilter.GaussianBlur(max(size // 48, 6)))
    image.alpha_composite(overlay)

    draw.line(line, fill=WHITE, width=max(size // 22, 8), joint="curve")
    for index, point in enumerate(line):
        fill = WARM if index == len(line) - 1 else ACCENT
        draw.ellipse(
            (
                point[0] - size * 0.019,
                point[1] - size * 0.019,
                point[0] + size * 0.019,
                point[1] + size * 0.019,
            ),
            fill=fill,
            outline=(255, 255, 255, 220),
            width=max(size // 160, 2),
        )


def make_icon_base(size):
    image = gradient(size)
    draw = ImageDraw.Draw(image)
    add_grid(draw, size)
    image = add_radial_glow(image, (int(size * 0.22), int(size * 0.22)), int(size * 0.22), ACCENT, 110)
    image = add_radial_glow(image, (int(size * 0.78), int(size * 0.8)), int(size * 0.18), WARM, 100)
    draw_chart_mark(image, inset_ratio=0.17)
    draw_wordmark(image, "V2", y_ratio=0.77, scale=0.18)
    return image


def rounded_icon(size):
    base = make_icon_base(size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=int(size * 0.22), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(base, (0, 0), mask)
    return output


def adaptive_foreground(size):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge_size = int(size * 0.7)
    badge = rounded_icon(badge_size)
    offset = ((size - badge_size) // 2, (size - badge_size) // 2)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    x, y = offset
    sdraw.rounded_rectangle(
        (x + size * 0.01, y + size * 0.045, x + badge_size - size * 0.01, y + badge_size + size * 0.025),
        radius=int(size * 0.15),
        fill=(5, 15, 30, 110),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(size // 36, 4)))
    image.alpha_composite(shadow)
    image.alpha_composite(badge, offset)
    return image


def legacy_android_icon(size):
    image = rounded_icon(size)
    return image


def splash_image(width, height):
    image = Image.new("RGBA", (width, height), BG_TOP + (255,))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(lerp(BG_TOP[i], BG_BOTTOM[i], t) for i in range(3)) + (255,)
        draw.line((0, y, width, y), fill=color)

    image = add_radial_glow(image, (int(width * 0.18), int(height * 0.2)), int(min(width, height) * 0.22), ACCENT, 110)
    image = add_radial_glow(image, (int(width * 0.78), int(height * 0.78)), int(min(width, height) * 0.18), WARM, 90)
    grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid)
    spacing = max(min(width, height) // 12, 32)
    for x in range(0, width + 1, spacing):
        gdraw.line((x, 0, x, height), fill=(255, 255, 255, 16), width=1)
    for y in range(0, height + 1, spacing):
        gdraw.line((0, y, width, y), fill=(255, 255, 255, 16), width=1)
    image.alpha_composite(grid)

    mark_size = int(min(width, height) * 0.28)
    mark = rounded_icon(mark_size)
    image.alpha_composite(mark, ((width - mark_size) // 2, int(height * 0.19)))

    text = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(text)
    title_font = load_font(max(int(min(width, height) * 0.08), 42), bold=True)
    sub_font = load_font(max(int(min(width, height) * 0.03), 22))
    title = "Refactor V2"
    subtitle = "Quant Trading Workspace"
    tb = tdraw.textbbox((0, 0), title, font=title_font)
    sb = tdraw.textbbox((0, 0), subtitle, font=sub_font)
    title_x = (width - (tb[2] - tb[0])) / 2
    title_y = height * 0.58
    sub_x = (width - (sb[2] - sb[0])) / 2
    sub_y = title_y + (tb[3] - tb[1]) + min(width, height) * 0.03
    tdraw.text((title_x, title_y), title, font=title_font, fill=WHITE)
    tdraw.text((sub_x, sub_y), subtitle, font=sub_font, fill=(214, 231, 255, 210))
    text = text.filter(ImageFilter.GaussianBlur(0.2))
    image.alpha_composite(text)
    return image


def save(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f"wrote {path.relative_to(ROOT)}")


def generate_macos_iconset():
    icon = rounded_icon(1024)
    save(icon, MAC_ICON_PNG)

    iconset_targets = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }

    MAC_ICONSET_DIR.mkdir(parents=True, exist_ok=True)
    for filename, size in iconset_targets.items():
        resized = icon.resize((size, size), Image.Resampling.LANCZOS)
        save(resized, MAC_ICONSET_DIR / filename)

    iconutil = shutil.which("iconutil")
    if not iconutil:
        print("iconutil not found; skipped build/icon.icns generation")
        return

    if MAC_ICON_ICNS.exists():
        MAC_ICON_ICNS.unlink()

    subprocess.run(
        [iconutil, "-c", "icns", str(MAC_ICONSET_DIR), "-o", str(MAC_ICON_ICNS)],
        check=True,
    )
    print(f"wrote {MAC_ICON_ICNS.relative_to(ROOT)}")


def main():
    save(rounded_icon(1024), IOS_ICON)
    generate_macos_iconset()

    ios_splash = splash_image(2732, 2732)
    for name in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
        save(ios_splash, IOS_SPLASH_DIR / name)

    for density, size in {
        "mdpi": 48,
        "hdpi": 72,
        "xhdpi": 96,
        "xxhdpi": 144,
        "xxxhdpi": 192,
    }.items():
        save(legacy_android_icon(size), ANDROID_RES / f"mipmap-{density}/ic_launcher.png")
        save(legacy_android_icon(size), ANDROID_RES / f"mipmap-{density}/ic_launcher_round.png")

    for density, size in {
        "mdpi": 108,
        "hdpi": 162,
        "xhdpi": 216,
        "xxhdpi": 324,
        "xxxhdpi": 432,
    }.items():
        save(adaptive_foreground(size), ANDROID_RES / f"mipmap-{density}/ic_launcher_foreground.png")

    splash_targets = {
        "drawable/splash.png": (480, 320),
        "drawable-port-mdpi/splash.png": (320, 480),
        "drawable-port-hdpi/splash.png": (480, 800),
        "drawable-port-xhdpi/splash.png": (720, 1280),
        "drawable-port-xxhdpi/splash.png": (960, 1600),
        "drawable-port-xxxhdpi/splash.png": (1280, 1920),
        "drawable-land-mdpi/splash.png": (480, 320),
        "drawable-land-hdpi/splash.png": (800, 480),
        "drawable-land-xhdpi/splash.png": (1280, 720),
        "drawable-land-xxhdpi/splash.png": (1600, 960),
        "drawable-land-xxxhdpi/splash.png": (1920, 1280),
    }
    for relative_path, size in splash_targets.items():
        save(splash_image(*size), ANDROID_RES / relative_path)


if __name__ == "__main__":
    main()
