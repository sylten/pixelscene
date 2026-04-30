"""
render_check.py — render the scene and diff against the reference image.

Usage:
    python3 render_check.py             # render current scene
    python3 render_check.py --clean     # apply positional sky cleaning then render
    python3 render_check.py --diff      # render + side-by-side diff with reference
"""
import os, sys, re, argparse
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

sys.modules['config'] = type('c', (), {
    'RENDER_WIDTH': 240, 'RENDER_HEIGHT': 160,
    'DISPLAY_WIDTH': 480, 'DISPLAY_HEIGHT': 320,
    'SCALE': 2, 'TARGET_FPS': 12,
    'DEFAULT_SCENE': 'forest', 'LOG_LEVEL': 'WARNING',
    'DISPLAY_DRIVER': 'sdl', 'FRAMEBUFFER': '/dev/fb0',
    'HTTP_HOST': '0.0.0.0', 'HTTP_PORT': 5000,
})()

import pygame
pygame.init()
pygame.display.set_mode((480, 320))

from PIL import Image, ImageDraw
import sprites as sp

REFERENCE = 'scene_reference.png'
OUT_SCENE  = '/tmp/render_current.png'
OUT_DIFF   = '/tmp/render_diff.png'
SCALE = 2  # for output images


# ---------------------------------------------------------------------------
# Sky detection — based on reference pixel colour, not palette index
# ---------------------------------------------------------------------------

def is_sky_pixel(r, g, b):
    """True if this reference pixel is pure sky/cloud background (no foreground content).

    Calibrated against actual reference samples in the mountains artifact zone.
    Lake water: B+G ≈ 230 (dark navy), rock/vegetation: green or brown dominant.
    Sky blue (55,116,185): B+G=301. Cloud haze: B+G=280-420, still blue-dominant.
    """
    # Bright sky blue: close to (55,116,185)
    if b > 160 and g > 90 and r < 90 and b > g > r:
        return True
    # Cloud haze / light sky: blue-dominant with sufficient brightness
    # B+G > 280 distinguishes sky haze (281-420) from dark lake water (≤242) and shadows
    if b > g > r and (b + g) > 280 and r < 160:
        return True
    # Light sky-teal (e.g. 163,205,198 or 134,170,160): high brightness regardless of B/G order
    # Rock/vegetation tops out at R+G+B ≈ 420; sky-teal is 450+
    if r + g + b > 450 and r < 175:
        return True
    # Near-white cloud highlights
    if r > 180 and g > 200 and b > 195:
        return True
    return False


# ---------------------------------------------------------------------------
# Positional cleaning — uses reference as oracle
# ---------------------------------------------------------------------------

def clean_sprite(pixels, w, h, scene_x, scene_y, ref_img):
    """Zero out pixels where the reference shows sky at that scene position."""
    ref_w, ref_h = ref_img.size
    cleaned = list(pixels)
    for sy in range(h):
        for sx in range(w):
            idx = sy * w + sx
            if cleaned[idx] == 0:
                continue
            rx, ry = scene_x + sx, scene_y + sy
            if 0 <= rx < ref_w and 0 <= ry < ref_h:
                r, g, b, a = ref_img.getpixel((rx, ry))
                if is_sky_pixel(r, g, b):
                    cleaned[idx] = 0
    return cleaned


def apply_positional_cleaning():
    """Clean MOUNTAINS, MID_VEGETATION, LAKE, GIANT_TREE by reference comparison."""
    ref = Image.open(REFERENCE).convert('RGBA')

    sprites_to_clean = [
        ('MOUNTAINS',     sp.MOUNTAINS,     sp.MOUNTAINS_W,     sp.MOUNTAINS_H,     0,  22),
        ('MID_VEGETATION',sp.MID_VEGETATION,sp.MID_VEGETATION_W,sp.MID_VEGETATION_H,0,  65),
        ('LAKE',          sp.LAKE,          sp.LAKE_W,          sp.LAKE_H,          28, 58),
        ('GIANT_TREE',    sp.GIANT_TREE,    sp.GIANT_TREE_W,    sp.GIANT_TREE_H,    135,18),
        ('CANOPY',        sp.CANOPY,        sp.CANOPY_W,        sp.CANOPY_H,        0,   0),
    ]

    def make_block(name, w, h, pixels, comment='1 frame'):
        lines = [f'# {name}: {w}x{h}, {comment}',
                 f'{name}_W, {name}_H = {w}, {h}',
                 f'{name} = [']
        for y in range(h):
            row = pixels[y*w:(y+1)*w]
            lines.append('    ' + ', '.join(str(v) for v in row) + ',')
        lines.append(']')
        return '\n'.join(lines)

    with open('sprites.py', 'r') as f:
        content = f.read()

    for name, pixels, w, h, sx, sy in sprites_to_clean:
        cleaned = clean_sprite(pixels, w, h, sx, sy, ref)
        changed = sum(1 for a, b in zip(pixels, cleaned) if a != b)
        print(f'  {name}: {changed} pixels cleared ({changed*100//len(pixels)}%)')

        comment = 'animate this in engine' if name == 'LAKE' else '1 frame'
        new_block = make_block(name, w, h, cleaned, comment)

        pat = rf'# {name}:.*?\n{name}_W.*?\n{name} = \[.*?\]'
        content = re.sub(pat, new_block, content, flags=re.DOTALL)

    with open('sprites.py', 'w') as f:
        f.write(content)
    print('sprites.py updated')


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_scene(no_clouds=False, advance_frames=60):
    from engine import sprite_loader
    sprite_loader._cache.clear()
    from engine.scene import Scene

    scene = Scene('scenes/forest')
    if no_clouds:
        scene.layers = [l for l in scene.layers if l.id != 'clouds']

    surf = pygame.Surface((240, 160))
    for _ in range(advance_frames):
        scene.update(1/12)
    scene.draw(surf)

    scaled = pygame.transform.scale(surf, (480, 320))
    raw = pygame.image.tostring(scaled, 'RGB')
    return Image.frombytes('RGB', (480, 320), raw)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def make_diff(rendered: Image.Image, reference_path: str) -> Image.Image:
    ref_raw = Image.open(reference_path).convert('RGB')
    ref = ref_raw.resize((480, 320), Image.NEAREST)

    W, H = 480, 320
    # Side-by-side: rendered | reference | diff-highlight
    out = Image.new('RGB', (W * 3, H))
    out.paste(rendered, (0, 0))
    out.paste(ref, (W, 0))

    diff = Image.new('RGB', (W, H))
    rp, refp, dp = rendered.load(), ref.load(), diff.load()
    max_diff = 0
    for y in range(H):
        for x in range(W):
            r1, g1, b1 = rp[x, y]
            r2, g2, b2 = refp[x, y]
            d = ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5
            max_diff = max(max_diff, d)
            intensity = min(255, int(d * 2))
            if d > 30:
                dp[x, y] = (intensity, 0, 0)  # red = different from reference
            else:
                dp[x, y] = (r1//4, g1//4, b1//4)  # dark = same

    out.paste(diff, (W * 2, 0))
    print(f'Max pixel diff from reference: {max_diff:.0f}')
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clean', action='store_true', help='Apply positional cleaning first')
    parser.add_argument('--diff',  action='store_true', help='Generate side-by-side diff with reference')
    parser.add_argument('--no-clouds', action='store_true', help='Skip cloud layer when rendering')
    parser.add_argument('--frames', type=int, default=60, help='Frames to advance before snapshot')
    args = parser.parse_args()

    if args.clean:
        print('Applying positional sky cleaning...')
        apply_positional_cleaning()
        # Reload the module so we get the cleaned data
        import importlib
        import sprites
        importlib.reload(sprites)

    print('Rendering scene...')
    img = render_scene(no_clouds=args.no_clouds, advance_frames=args.frames)
    img.save(OUT_SCENE)
    print(f'Saved: {OUT_SCENE}')

    if args.diff:
        print('Generating diff...')
        diff_img = make_diff(img, REFERENCE)
        diff_img.save(OUT_DIFF)
        print(f'Saved diff: {OUT_DIFF}  (left=render, mid=reference, right=diff in red)')
