#!/usr/bin/env python3
"""Generate placeholder sprite assets so the scene runs without real art."""
import os
from PIL import Image, ImageDraw


def sprite_sheet(path: str, frame_count: int, fw: int, fh: int, color: tuple):
    img = Image.new("RGBA", (frame_count * fw, fh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r, g, b = color
    for i in range(frame_count):
        t = i / max(frame_count - 1, 1)
        cr = int(r * (0.5 + 0.5 * t))
        cg = int(g * (0.5 + 0.5 * t))
        cb = int(b * (0.5 + 0.5 * t))
        x0, y0 = i * fw, 0
        x1, y1 = x0 + fw - 1, fh - 1
        draw.rectangle([x0, y0, x1, y1], fill=(cr, cg, cb, 210))
        draw.rectangle([x0, y0, x1, y1], outline=(255, 255, 255, 180))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print(f"  {path}")


def make_background():
    w, h = 240, 160
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    # Sky gradient
    for y in range(80):
        t = y / 80
        color = (int(80 + 60 * t), int(140 + 60 * t), int(200 + 40 * t))
        draw.line([(0, y), (w, y)], fill=color)

    # Ground gradient
    for y in range(80, h):
        t = (y - 80) / 80
        color = (int(30 + 10 * t), int(90 - 20 * t), int(30 + 10 * t))
        draw.line([(0, y), (w, y)], fill=color)

    # Mountains
    draw.polygon([(0, 80), (50, 45), (100, 80)], fill=(70, 90, 70))
    draw.polygon([(80, 80), (140, 32), (200, 80)], fill=(80, 105, 80))
    draw.polygon([(170, 80), (220, 50), (240, 80)], fill=(65, 85, 65))
    # Snow caps
    draw.polygon([(50, 45), (60, 55), (40, 55)], fill=(230, 235, 240))
    draw.polygon([(140, 32), (154, 46), (126, 46)], fill=(230, 235, 240))

    os.makedirs("assets/backgrounds", exist_ok=True)
    img.save("assets/backgrounds/overworld_bg.png")
    print("  assets/backgrounds/overworld_bg.png")


def make_clouds():
    img = Image.new("RGBA", (128, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for cx, cy, rx, ry in [(20, 16, 16, 10), (56, 12, 20, 12), (96, 18, 14, 9)]:
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(230, 235, 245, 200))
    os.makedirs("assets/sprites/environment", exist_ok=True)
    img.save("assets/sprites/environment/clouds.png")
    print("  assets/sprites/environment/clouds.png")


print("Generating placeholder assets...")

make_background()
make_clouds()

sprite_sheet("assets/sprites/characters/traveler.png", 6, 16, 24, (80, 140, 220))

sprite_sheet("assets/sprites/effects/traveler_arrive.png",  8, 16, 24, (100, 200, 100))
sprite_sheet("assets/sprites/effects/chest_open.png",       6, 16, 16, (200, 160,  40))
sprite_sheet("assets/sprites/effects/coins_arc.png",       10, 16, 16, (255, 220,   0))
sprite_sheet("assets/sprites/effects/comet.png",           12, 32, 32, (255, 140,  20))
sprite_sheet("assets/sprites/effects/impact_smoke.png",     8, 48, 32, (170, 170, 170))
sprite_sheet("assets/sprites/effects/ship_launch.png",     14, 32, 32, (100, 180, 255))
sprite_sheet("assets/sprites/effects/fireworks.png",       20, 32, 32, (255,  80, 200))
sprite_sheet("assets/sprites/effects/character_leave.png", 10, 16, 24, (180, 100,  80))

os.makedirs("assets/tilesets", exist_ok=True)
print("Done.")
