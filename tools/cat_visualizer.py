#!/usr/bin/env python3
"""
Cat surface + transition visualizer.
Run from the project root: python3 tools/cat_visualizer.py

Shows the city scene with each cat surface drawn as a coloured band,
waypoints as dots, and transitions as jump arcs / offscreen arrows.
A legend is printed to stdout. No font rendering (avoids pygame.font
circular-import bug on Python 3.14).

Controls:
  ESC / Q     quit
  SPACE       toggle scene background on/off
  S           save a screenshot to cat_surfaces.png
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import pygame

SCALE = 3
W = config.RENDER_WIDTH * SCALE
H = config.RENDER_HEIGHT * SCALE

SURFACE_COLORS = {
    "pavement":        ( 80, 210,  80),
    "roof_red":        (255, 100, 100),
    "roof_skyscraper": (100, 160, 255),
    "roof_blue":       ( 80, 220, 220),
    "roof_bar":        (255, 190,  60),
}
DEFAULT_COLOR   = (200, 200, 200)
JUMP_COLOR      = (255, 255,  80)   # yellow
OFFSCREEN_COLOR = (220, 140, 255)   # purple


def s(x, y=None):
    if y is None:
        return int(x * SCALE)
    return (int(x * SCALE), int(y * SCALE))


def draw_dashed_line(surf, color, p1, p2, width=2, dash=8):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    steps = max(1, int(length / dash))
    for i in range(steps):
        t0, t1 = i / steps, (i + 0.5) / steps
        a = (int(p1[0] + dx * t0), int(p1[1] + dy * t0))
        b = (int(p1[0] + dx * t1), int(p1[1] + dy * t1))
        pygame.draw.line(surf, color, a, b, width)


def draw_arrowhead(surf, color, tip, prev, size=8):
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    left  = (tip[0] - ux * size + px * size // 2, tip[1] - uy * size + py * size // 2)
    right = (tip[0] - ux * size - px * size // 2, tip[1] - uy * size - py * size // 2)
    pygame.draw.polygon(surf, color, [
        (int(tip[0]),   int(tip[1])),
        (int(left[0]),  int(left[1])),
        (int(right[0]), int(right[1])),
    ])


def draw_jump_arc(surf, color, from_xy, to_xy):
    fx, fy = from_xy
    tx, ty = to_xy
    drop = abs(ty - fy)
    arc  = max(s(8), int(drop * 0.15))
    pts  = []
    for i in range(41):
        t = i / 40
        x = fx + (tx - fx) * t
        y = fy + (ty - fy) * t - arc * math.sin(math.pi * t)
        pts.append((int(x), int(y)))
    pygame.draw.lines(surf, color, False, pts, 2)
    draw_arrowhead(surf, color, pts[-1], pts[-2], size=8)
    # dot at launch and land
    pygame.draw.circle(surf, color, (int(fx), int(fy)), 4)
    pygame.draw.circle(surf, color, (int(tx), int(ty)), 4)


def render_scene_background(scene_dir):
    from engine.scene import Scene
    scene = Scene(scene_dir)
    buf = pygame.Surface((config.RENDER_WIDTH, config.RENDER_HEIGHT))
    scene.draw(buf)
    return pygame.transform.scale(buf, (W, H))


def print_legend(surfaces):
    print("\n── Cat surfaces ─────────────────────────────────────")
    for name, col in SURFACE_COLORS.items():
        if name in surfaces:
            sd = surfaces[name]
            if "depth_y_far" in sd:
                pos = f"y {sd['depth_y_far']}–{sd['depth_y_near']} (full width)"
            else:
                pos = f"y={sd['y']}  x={sd['x_min']}–{sd['x_max']}  persp={sd.get('persp','?')}"
            print(f"  {name:<18} {pos}")
    print("\n── Transitions ──────────────────────────────────────")
    for name, sd in surfaces.items():
        for tr in sd.get("transitions", []):
            via = tr["via"]
            to  = tr["to"]
            if via == "jump":
                print(f"  {name:<18} --jump-arc-->  {to}  "
                      f"(from_x={tr.get('from_x','?')} land_x={tr.get('land_x','?')} land_y={tr.get('land_y','?')})")
            else:
                print(f"  {name:<18} --offscreen->  {to}  "
                      f"(exit={tr.get('exit_side','?')} entry={tr.get('entry_x','?')},{tr.get('entry_y','?')})")
    print()
    print("yellow arcs  = jump transitions")
    print("purple dashes = offscreen teleport (exit arrow + entry arrow)")
    print()
    print("Controls: SPACE toggle bg | S save screenshot | ESC/Q quit")
    print("─────────────────────────────────────────────────────\n")


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Cat visualizer — SPACE=toggle bg  S=save  ESC=quit")

    scene_dir  = os.path.join(os.path.dirname(__file__), "..", "scenes", "city")
    scene_path = os.path.join(scene_dir, "scene.json")

    with open(scene_path) as f:
        scene_data = json.load(f)

    cat_def  = next(l for l in scene_data["layers"] if l["id"] == "cat")
    surfaces = cat_def["surfaces"]

    print_legend(surfaces)

    print("Loading scene background…")
    try:
        bg = render_scene_background(scene_dir)
        print("Background ready.")
    except Exception as e:
        print(f"Could not render background ({e}) — using plain fill.")
        bg = None

    show_bg = True
    clock   = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    show_bg = not show_bg
                elif event.key == pygame.K_s:
                    pygame.image.save(screen, "cat_surfaces.png")
                    print("Saved cat_surfaces.png")

        # background
        screen.blit(bg, (0, 0)) if (show_bg and bg) else screen.fill((18, 32, 85))

        # translucent overlay for surface bands
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)

        for name, sd in surfaces.items():
            col   = SURFACE_COLORS.get(name, DEFAULT_COLOR)
            a_col = (*col, 55)
            b_col = (*col, 210)

            if "depth_y_far" in sd:
                y0 = s(sd["depth_y_far"])
                y1 = s(sd["depth_y_near"])
                pygame.draw.rect(overlay, a_col, pygame.Rect(0, y0, W, y1 - y0))
                pygame.draw.rect(overlay, b_col, pygame.Rect(0, y0, W, y1 - y0), 2)
                for wp in sd.get("waypoints", []):
                    pygame.draw.circle(overlay, (*col, 230), s(wp[0], wp[1]), s(2))
            else:
                y_top  = s(sd["y"])
                x0, x1 = s(sd["x_min"]), s(sd["x_max"])
                band_h = max(4, s(3))
                pygame.draw.rect(overlay, a_col, pygame.Rect(x0, y_top, x1 - x0, band_h))
                pygame.draw.rect(overlay, b_col, pygame.Rect(x0, y_top, x1 - x0, band_h), 2)
                # small tick at x_min and x_max
                pygame.draw.line(overlay, b_col, (x0, y_top - s(3)), (x0, y_top + band_h + s(3)), 2)
                pygame.draw.line(overlay, b_col, (x1, y_top - s(3)), (x1, y_top + band_h + s(3)), 2)

        screen.blit(overlay, (0, 0))

        # transitions
        for name, sd in surfaces.items():
            if "depth_y_far" in sd:
                src_y  = (sd["depth_y_far"] + sd["depth_y_near"]) / 2
                src_cx = config.RENDER_WIDTH / 2
            else:
                src_y  = sd["y"]
                src_cx = (sd["x_min"] + sd["x_max"]) / 2

            for tr in sd.get("transitions", []):
                via = tr["via"]
                to  = tr["to"]
                dst = surfaces[to]
                dst_col = SURFACE_COLORS.get(to, DEFAULT_COLOR)

                if "depth_y_far" in dst:
                    dst_y  = (dst["depth_y_far"] + dst["depth_y_near"]) / 2
                else:
                    dst_y  = dst["y"]

                if via == "jump":
                    from_x = tr.get("from_x", src_cx)
                    land_x = tr.get("land_x", (dst.get("x_min", 0) + dst.get("x_max", 240)) / 2)
                    land_y = tr.get("land_y", dst_y)
                    draw_jump_arc(screen, JUMP_COLOR, s(from_x, src_y), s(land_x, land_y))

                elif via == "offscreen":
                    exit_side = tr.get("exit_side", "right")
                    entry_x   = tr.get("entry_x", (dst.get("x_min", 0) + dst.get("x_max", 240)) / 2)
                    entry_y   = tr.get("entry_y", dst_y)

                    # exit: dashed arrow from surface centre to screen edge
                    edge_x = 0 if exit_side == "left" else W
                    draw_dashed_line(screen, OFFSCREEN_COLOR,
                                     s(src_cx, src_y), (edge_x, s(src_y)))
                    draw_arrowhead(screen, OFFSCREEN_COLOR,
                                   (edge_x, s(src_y)), s(src_cx, src_y))

                    # entry: dashed arrow from screen edge to landing spot
                    entry_edge = s(3) if exit_side == "left" else W - s(3)
                    draw_dashed_line(screen, dst_col,
                                     (entry_edge, s(entry_y)), s(entry_x, entry_y))
                    draw_arrowhead(screen, dst_col,
                                   s(entry_x, entry_y), (entry_edge, s(entry_y)))

        # corner legend squares (no text — see stdout)
        items = list(SURFACE_COLORS.items()) + [
            ("jump arc",  JUMP_COLOR),
            ("offscreen", OFFSCREEN_COLOR),
        ]
        for i, (name, col) in enumerate(items):
            pygame.draw.rect(screen, col, pygame.Rect(4, 4 + i * 12, 10, 10))
            pygame.draw.rect(screen, (0, 0, 0), pygame.Rect(4, 4 + i * 12, 10, 10), 1)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
