#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Banner generator and sender for /barygos

Generates five PNG banners (1280x720) with the words "apsisaugok" and "crypto",
optimized to look strong in Telegram image posts on mobile.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os, random

W, H = 1280, 720
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


def variant1():
    img = radial_grad((5, 8, 20), (18, 10, 45))
    img = add_grid(img, step=46, color=(120, 200, 255), alpha=22)
    f1 = load_font(170)
    f2 = load_font(74)
    d = ImageDraw.Draw(img)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    img = glow_layer(img, PRIMARY.upper(), f1, (x, y), color=(60, 220, 255), radius=18, passes=3, alpha=140)
    d = ImageDraw.Draw(img)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(230, 255, 255), stroke_fill=(40, 120, 255), stroke_w=3)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 30
    img = glow_layer(img, SECONDARY.upper(), f2, (sx, sy), color=(200, 120, 255), radius=10, passes=2, alpha=130)
    d = ImageDraw.Draw(img)
    d.text((sx, sy), SECONDARY.upper(), font=f2, fill=(245, 230, 255))
    img.save("barygos_1.png")


def variant2():
    bg = linear_grad((10, 10, 12), (33, 33, 38))
    bg = add_sparkles(bg, 70)
    d = ImageDraw.Draw(bg)
    f1 = load_font(160)
    f2 = load_font(66)
    gold = gold_gradient_text(PRIMARY.upper(), f1)
    bg = Image.alpha_composite(bg.convert("RGBA"), gold).convert("RGB")
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(255, 255, 255, 0), stroke_fill=(30, 18, 0), stroke_w=2)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 36
    stroke_text(d, (sx, sy), SECONDARY.upper(), f2, fill=(240, 210, 120), stroke_fill=(50, 35, 10), stroke_w=2)
    bg.save("barygos_2.png")


def variant3():
    base = linear_grad((5, 5, 6), (12, 16, 28))
    d = ImageDraw.Draw(base)
    f1 = load_font(176)
    f2 = load_font(64)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    y -= 10
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(180, 255, 200), stroke_fill=(0, 0, 0), stroke_w=5)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 28
    stroke_text(d, (sx, sy), SECONDARY.upper(), f2, fill=(130, 220, 255), stroke_fill=(0, 0, 0), stroke_w=3)
    out = glitch(base, strength=22, bands=22)
    out.save("barygos_3.png")


def variant4():
    under = radial_grad((12, 12, 12), (4, 4, 4))
    striped = diagonal_stripes(under, color1=(245, 205, 0), color2=(16, 16, 16), stripe_w=38)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    img = Image.alpha_composite(striped.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(img)
    f1 = load_font(150)
    f2 = load_font(70)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    stroke_text(d, (x, y), PRIMARY.upper(), f1, fill=(240, 240, 240), stroke_fill=(180, 0, 0), stroke_w=6)
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 24
    small_tag(d, SECONDARY.upper(), sx - 40, sy, fill=(10, 10, 10), bg=(245, 205, 0))
    img.save("barygos_4.png")


def variant5():
    base = Image.new("RGB", (W, H))
    p = base.load()
    for y in range(H):
        for x in range(W):
            t = (math.sin(x / 80) + math.cos(y / 90)) / 2 + 0.5
            r = int(200 + 55 * math.sin((x + y) / 140))
            g = int(120 + 90 * t)
            b = int(220 + 30 * math.cos(x / 110))
            p[x, y] = (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
            )
    base = base.filter(ImageFilter.GaussianBlur(2))
    d = ImageDraw.Draw(base)
    f1 = load_font(160)
    f2 = load_font(70)
    x, y, tw, th = center_xy(d, PRIMARY.upper(), f1)
    for i in range(10, 0, -1):
        d.text((x + i, y + i), PRIMARY.upper(), font=f1, fill=(25, 25, 45))
    base = glow_layer(base, PRIMARY.upper(), f1, (x, y), color=(255, 160, 240), radius=12, passes=2, alpha=140)
    d = ImageDraw.Draw(base)
    d.text((x, y), PRIMARY.upper(), font=f1, fill=(255, 255, 255))
    sx, sy, *_ = center_xy(d, SECONDARY.upper(), f2)
    sy = y + th + 20
    d.text((sx, sy), SECONDARY.upper(), font=f2, fill=(255, 240, 240))
    base.save("barygos_5.png")


def generate_all():
    variant1(); variant2(); variant3(); variant4(); variant5()
    return [f"barygos_{i}.png" for i in range(1, 6)]


if __name__ == "__main__":
    files = generate_all()
    print("Saved:", ", ".join(files))


