#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Banner generator and sender for /barygos

Generates five PNG banners (1280x720) with the words "apsisaugok" and "crypto",
optimized to look strong in Telegram image posts on mobile.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os, random

# Higher resolution for cleaner Telegram compression
W, H = 1920, 1080
PRIMARY = "apsisaugok"
SECONDARY = "crypto"

FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "arialbd.ttf",
]


def load_font(size: int):
    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def center_xy(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return (W - tw) // 2, (H - th) // 2, tw, th


def stroke_text(draw, xy, text, font, fill, stroke_fill, stroke_w=3):
    x, y = xy
    for dx, dy in [
        (-stroke_w, 0),
        (stroke_w, 0),
        (0, -stroke_w),
        (0, stroke_w),
        (-stroke_w, -stroke_w),
        (stroke_w, stroke_w),
        (-stroke_w, stroke_w),
        (stroke_w, -stroke_w),
    ]:
        draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def glow_layer(base, text, font, xy, color=(0, 255, 255), radius=16, passes=3, alpha=140):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(passes):
        d.text(xy, text, font=font, fill=color + (alpha,))
        layer = layer.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def linear_grad(c1, c2):
    img = Image.new("RGB", (W, H))
    p = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        for x in range(W):
            p[x, y] = (r, g, b)
    return img


def radial_grad(c_in, c_out, cx=W // 2, cy=H // 2):
    img = Image.new("RGB", (W, H))
    p = img.load()
    maxd = math.hypot(max(cx, W - cx), max(cy, H - cy))
    for y in range(H):
        for x in range(W):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            r = int(c_in[0] * (1 - t) + c_out[0] * t)
            g = int(c_in[1] * (1 - t) + c_out[1] * t)
            b = int(c_in[2] * (1 - t) + c_out[2] * t)
            p[x, y] = (r, g, b)
    return img


def add_grid(img, step=40, color=(255, 255, 255), alpha=25):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(0, W, step):
        d.line((x, 0, x, H), fill=color + (alpha,), width=1)
    for y in range(0, H, step):
        d.line((0, y, W, y), fill=color + (alpha,), width=1)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def gold_gradient_text(text, font, tint_top=(255, 220, 90), tint_bot=(200, 140, 20)):
    temp = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(temp)
    x, y, tw, th = center_xy(d, text, font)
    d.text((x, y), text, font=font, fill=255)
    grad = Image.new("RGBA", (tw, th))
    gd = ImageDraw.Draw(grad)
    for yy in range(th):
        t = yy / max(1, th - 1)
        r = int(tint_top[0] * (1 - t) + tint_bot[0] * t)
        g = int(tint_top[1] * (1 - t) + tint_bot[1] * t)
        b = int(tint_top[2] * (1 - t) + tint_bot[2] * t)
        gd.line([(0, yy), (tw, yy)], fill=(r, g, b, 255), width=1)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(grad, (x, y), mask=temp.crop((x, y, x + tw, y + th)))
    return out


def add_sparkles(img, n=80):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(n):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        r = random.randint(1, 3)
        c = (255, 255, 255, random.randint(80, 160))
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def glitch(img, strength=10, bands=18):
    img = img.convert("RGB")
    out = img.copy()
    for _ in range(bands):
        y = random.randint(0, H - 5)
        h = random.randint(2, 12)
        off = random.randint(-strength, strength)
        slice_ = img.crop((0, y, W, y + h))
        out.paste(slice_, (off, y))
    return out


def diagonal_stripes(bg, color1=(245, 215, 0), color2=(10, 10, 10), stripe_w=36):
    ov = Image.new("RGB", (W, H), color2)
    d = ImageDraw.Draw(ov)
    diag_len = int(math.hypot(W, H)) + stripe_w
    for i in range(-diag_len, diag_len, stripe_w * 2):
        d.polygon([(i, 0), (i + stripe_w, 0), (i + H + stripe_w, W), (i + H, W)], fill=color1)
    mix = Image.blend(ov, bg, 0.35)
    return mix


def small_tag(draw, text, x, y, fill=(0, 0, 0), bg=(255, 255, 255)):
    font = load_font(44)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 16
    draw.rounded_rectangle((x, y, x + tw + 2 * pad, y + th + 2 * pad), radius=18, fill=bg)
    draw.text((x + pad, y + pad), text, font=font, fill=fill)


def vignette(img, strength=0.6):
    """Darken edges to create depth."""
    mask = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(mask)
    r = int(max(W, H) * 0.65)
    d.ellipse((W//2 - r, H//2 - r, W//2 + r, H//2 + r), fill=int(255 * (1 - strength)))
    mask = mask.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGB", (W, H), (10, 10, 15))
    return Image.composite(img, dark, mask)


def spray_noise_layer(alpha=70, scale=1.0):
    """Simulate spray paint texture."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    count = int(12000 * scale)
    for _ in range(count):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        r = random.randint(1, 2)
        a = random.randint(alpha // 3, alpha)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
    return ov.filter(ImageFilter.GaussianBlur(1))


def brick_wall(bg_color=(28, 28, 32), mortar=(60, 60, 65), brick=(33, 33, 40)):
    img = Image.new("RGB", (W, H), bg_color)
    d = ImageDraw.Draw(img)
    bw, bh = 180, 70
    for row in range(0, H + bh, bh):
        offset = (row // bh) % 2 * (bw // 2)
        for col in range(-bw, W + bw, bw):
            x1, y1 = col + offset, row
            x2, y2 = x1 + bw - 2, y1 + bh - 2
            d.rectangle((x1, y1, x2, y2), fill=brick)
    # mortar lines
    for y in range(0, H, bh):
        d.line((0, y, W, y), fill=mortar, width=2)
    for x in range(0, W, 180):
        d.line((x, 0, x, H), fill=mortar, width=2)
    return img.filter(ImageFilter.GaussianBlur(0.5))


def paint_drips(draw, x, y, width=320, color=(255, 60, 90), count=6):
    for _ in range(count):
        sx = x + random.randint(0, max(1, width - 1))
        length = random.randint(30, 140)
        thickness = random.randint(4, 10)
        draw.line((sx, y, sx, y + length), fill=color, width=thickness)


def perspective_extrude_text(img, text, font, base_pos, depth=36, dx=1.6, dy=1.0, color_front=(255, 255, 255), color_side=(40, 40, 60)):
    d = ImageDraw.Draw(img)
    x, y = base_pos
    # Side layers for depth
    for i in range(depth, 0, -1):
        c = (
            int(color_side[0] + (color_front[0] - color_side[0]) * (i / depth)),
            int(color_side[1] + (color_front[1] - color_side[1]) * (i / depth)),
            int(color_side[2] + (color_front[2] - color_side[2]) * (i / depth)),
        )
        d.text((x + i * dx, y + i * dy), text, font=font, fill=c)
    # Front face
    d.text((x, y), text, font=font, fill=color_front)
    return img


def variant1():
    """Graffiti on brick wall with neon glow and drips."""
    img = brick_wall()
    img = vignette(img, 0.55)
    img = Image.alpha_composite(img.convert("RGBA"), spray_noise_layer(alpha=55, scale=0.7)).convert("RGB")
    f1 = load_font(200)
    f2 = load_font(84)
    d = ImageDraw.Draw(img)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    y -= 80
    img = glow_layer(img, PRIMARY.upper(), f1, (x, y), color=(255, 80, 120), radius=22, passes=3, alpha=160)
    d = ImageDraw.Draw(img)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(245, 245, 245), stroke_fill=(20, 20, 30), stroke_w=6)
    paint_drips(d, x, y + th - 10, width=tw, color=(255, 60, 90), count=10)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 40
    d.text((sx, sy), SECONDARY.upper(), font=f2, fill=(240, 220, 220))
    img.save("barygos_1.png")


def variant2():
    """Deep extrude with perspective and chrome highlight."""
    bg = radial_grad((10, 12, 16), (0, 0, 0))
    bg = add_sparkles(bg, 40)
    f1 = load_font(220)
    f2 = load_font(78)
    d = ImageDraw.Draw(bg)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    y -= 40
    bg = perspective_extrude_text(bg, PRIMARY.upper(), f1, (x, y), depth=50, dx=2.4, dy=1.5, color_front=(250, 250, 255), color_side=(30, 40, 75))
    # Chrome highlight strip
    hl = Image.new("L", (tw, th), 0)
    hd = ImageDraw.Draw(hl)
    hd.rectangle((0, 0, tw, th // 2), fill=180)
    hl = hl.filter(ImageFilter.GaussianBlur(10))
    fg = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
    fg.putalpha(hl)
    bg.paste(fg, (x, y), fg)
    d = ImageDraw.Draw(bg)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 10
    stroke_text(d, (sx, sy), SECONDARY.upper(), f2, fill=(205, 240, 255), stroke_fill=(0, 0, 0), stroke_w=4)
    bg = vignette(bg, 0.6)
    bg.save("barygos_2.png")


def variant3():
    """Neo-graffiti with RGB split and spray texture."""
    base = linear_grad((12, 14, 26), (4, 6, 12))
    base = add_grid(base, step=58, color=(80, 120, 160), alpha=18)
    base = Image.alpha_composite(base.convert("RGBA"), spray_noise_layer(alpha=60, scale=1.1)).convert("RGB")
    d = ImageDraw.Draw(base)
    f1 = load_font(210)
    f2 = load_font(80)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    y -= 30
    # RGB split
    for off, col in [(-4, (255, 60, 60)), (4, (60, 180, 255))]:
        d.text((x + off, y), PRIMARY.upper(), font=f1, fill=col)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(240, 240, 240), stroke_fill=(0, 0, 0), stroke_w=5)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 24
    stroke_text(d, (sx, sy), SECONDARY.upper(), f2, fill=(210, 240, 255), stroke_fill=(0, 0, 0), stroke_w=3)
    out = glitch(base, strength=16, bands=18)
    out = vignette(out, 0.55)
    out.save("barygos_3.png")


def variant4():
    """Stencil warning + tape for street poster vibe."""
    under = radial_grad((18, 18, 18), (0, 0, 0))
    striped = diagonal_stripes(under, color1=(245, 205, 0), color2=(16, 16, 16), stripe_w=44)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 160))
    img = Image.alpha_composite(striped.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(img)
    f1 = load_font(190)
    f2 = load_font(88)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(245, 245, 245), stroke_fill=(20, 20, 20), stroke_w=10)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 14
    small_tag(d, SECONDARY.upper(), sx - 40, sy, fill=(15, 15, 15), bg=(245, 205, 0))
    img = vignette(img, 0.65)
    img.save("barygos_4.png")


def variant5():
    """Vapor holographic glass with bloom and 3D offset shadow."""
    base = Image.new("RGB", (W, H))
    p = base.load()
    for y in range(H):
        for x in range(W):
            t = (math.sin(x / 90) + math.cos(y / 120)) / 2 + 0.5
            r = int(220 + 35 * math.sin((x + y) / 160))
            g = int(140 + 80 * t)
            b = int(240 + 25 * math.cos(x / 140))
            p[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    base = base.filter(ImageFilter.GaussianBlur(2))
    d = ImageDraw.Draw(base)
    f1 = load_font(210)
    f2 = load_font(86)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    # Soft shadow offset
    for i in range(18, 0, -2):
        d.text((x + i, y + i), PRIMARY.upper(), font=f1, fill=(20, 20, 35))
    base = glow_layer(base, PRIMARY.upper(), f1, (x, y), color=(255, 160, 240), radius=18, passes=2, alpha=150)
    d = ImageDraw.Draw(base)
    d.text((x, y), PRIMARY.upper(), font=f1, fill=(255, 255, 255))
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 14
    d.text((sx, sy), SECONDARY.upper(), font=f2, fill=(250, 245, 255))
    base = vignette(base, 0.55)
    base.save("barygos_5.png")


def generate_all():
    variant1(); variant2(); variant3(); variant4(); variant5()
    return [f"barygos_{i}.png" for i in range(1, 6)]


if __name__ == "__main__":
    files = generate_all()
    print("Saved:", ", ".join(files))


