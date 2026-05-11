#!/usr/bin/env python3
"""
Scene entity path editor.
Run from the project root: python3 tools/scene_editor.py [scene_dir] [entity_id]

Renders the scene with entity surfaces, waypoints, and transitions overlaid.
Supports drag-and-drop editing of all path geometry.

Controls:
  Left-drag          move a handle (waypoint / band edge / transition endpoint)
  Left-click (empty) add waypoint on depth-band surfaces
  Right-click        delete hovered waypoint
  Delete/Backspace   delete selected waypoint
  Tab / Shift+Tab    cycle between editable entities in the scene
  S                  save edits to scene.json  (backup on first save per session)
  SPACE              toggle scene background
  ESC / Q            quit
"""

import colorsys
import hashlib
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import pygame

SCALE = config.SCALE
W = config.DISPLAY_WIDTH
H = config.DISPLAY_HEIGHT

JUMP_COLOR      = (255, 255,  80)
OFFSCREEN_COLOR = (220, 140, 255)


# ── Colour helpers ─────────────────────────────────────────────────────────────

def surface_color(name):
    """Deterministic per-name color derived from MD5 hash — stable across runs."""
    digest = hashlib.md5(name.encode()).digest()
    hue = int.from_bytes(digest[:2], "big") / 65536
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def handle_color(kind, surface_name):
    if kind in ("jump_from", "jump_land"):
        return JUMP_COLOR
    if kind == "offscreen_entry":
        return OFFSCREEN_COLOR
    return surface_color(surface_name)


# ── Coordinate helpers ─────────────────────────────────────────────────────────

def s(x, y=None):
    if y is None:
        return int(x * SCALE)
    return (int(x * SCALE), int(y * SCALE))


def unscale(dx, dy):
    return dx / SCALE, dy / SCALE


def clamp_scene(sx, sy):
    return (
        max(0.0, min(config.RENDER_WIDTH  - 1, sx)),
        max(0.0, min(config.RENDER_HEIGHT - 1, sy)),
    )


# ── Drawing helpers ────────────────────────────────────────────────────────────

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
    pygame.draw.circle(surf, color, (int(fx), int(fy)), 4)
    pygame.draw.circle(surf, color, (int(tx), int(ty)), 4)


# ── Scene background ───────────────────────────────────────────────────────────

def render_scene_background(scene_dir):
    from engine.scene import Scene
    scene = Scene(scene_dir)
    # SRCALPHA ensures proper compositing: SRCALPHA-onto-plain on macOS Metal
    # sets destination alpha=0 for covered pixels, making them invisible.
    # Using SRCALPHA buffer keeps every pixel opaque (alpha=255).
    buf = pygame.Surface((config.RENDER_WIDTH, config.RENDER_HEIGHT), pygame.SRCALPHA)
    scene.draw(buf)
    return pygame.transform.scale(buf, (W, H))


# ── Entity / handle model ──────────────────────────────────────────────────────

def collect_editable_layers(scene_data):
    return [l for l in scene_data["layers"] if "surfaces" in l]


def surface_center_y(sd):
    if "depth_y_far" in sd:
        return (sd["depth_y_far"] + sd["depth_y_near"]) / 2
    return sd["y"]


def build_handles(layer_def):
    """Return list of (kind, pos, surface_name, idx) tuples for all draggable handles."""
    handles = []
    surfaces = layer_def["surfaces"]
    mid_x = config.RENDER_WIDTH / 2

    for name, sd in surfaces.items():
        if "depth_y_far" in sd:
            handles.append(("depth_far",  (mid_x,        sd["depth_y_far"]),  name, None))
            handles.append(("depth_near", (mid_x,        sd["depth_y_near"]), name, None))
            for i, wp in enumerate(sd.get("waypoints", [])):
                handles.append(("waypoint", (wp[0], wp[1]), name, i))
        else:
            hx = (sd["x_min"] + sd["x_max"]) / 2
            handles.append(("fixed_y",    (hx,          sd["y"]),   name, None))
            handles.append(("fixed_xmin", (sd["x_min"], sd["y"]),   name, None))
            handles.append(("fixed_xmax", (sd["x_max"], sd["y"]),   name, None))

        src_y = surface_center_y(sd)
        for i, tr in enumerate(sd.get("transitions", [])):
            if tr["via"] == "jump":
                handles.append(("jump_from", (tr["from_x"],  src_y),         name, i))
                handles.append(("jump_land", (tr["land_x"],  tr["land_y"]),  name, i))
            elif tr["via"] == "offscreen":
                handles.append(("offscreen_entry", (tr["entry_x"], tr["entry_y"]), name, i))

    return handles


def hit_test(handles, dx, dy, radius=9):
    """Return (kind, surface_name, idx) of the closest handle within radius, or None."""
    best = None
    best_dist = radius + 1
    for kind, pos, surface_name, idx in reversed(handles):
        hx, hy = s(pos[0]), s(pos[1])
        dist = math.hypot(dx - hx, dy - hy)
        if dist <= radius and dist < best_dist:
            best = (kind, surface_name, idx)
            best_dist = dist
    return best


def apply_drag(drag_key, sx, sy, surfaces):
    """Mutate surfaces in place according to drag_key and new scene-space position."""
    kind, surface_name, idx = drag_key
    sd = surfaces[surface_name]
    sx, sy = clamp_scene(sx, sy)

    if kind == "waypoint":
        sd["waypoints"][idx] = [round(sx), round(sy)]
    elif kind == "depth_far":
        sd["depth_y_far"]  = min(round(sy), sd["depth_y_near"] - 1)
    elif kind == "depth_near":
        sd["depth_y_near"] = max(round(sy), sd["depth_y_far"]  + 1)
    elif kind == "fixed_y":
        sd["y"]     = round(sy)
    elif kind == "fixed_xmin":
        sd["x_min"] = min(round(sx), sd["x_max"] - 1)
    elif kind == "fixed_xmax":
        sd["x_max"] = max(round(sx), sd["x_min"] + 1)
    elif kind == "jump_from":
        sd["transitions"][idx]["from_x"] = round(sx)
    elif kind == "jump_land":
        sd["transitions"][idx]["land_x"] = round(sx)
        sd["transitions"][idx]["land_y"] = round(sy)
    elif kind == "offscreen_entry":
        sd["transitions"][idx]["entry_x"] = round(sx)
        sd["transitions"][idx]["entry_y"] = round(sy)


# ── Save ───────────────────────────────────────────────────────────────────────

def save_scene(scene_data, scene_path, backup_state):
    if not backup_state["done"]:
        bak = scene_path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(scene_path, bak)
        backup_state["done"] = True
    with open(scene_path, "w") as f:
        json.dump(scene_data, f, indent=2, sort_keys=False, ensure_ascii=False)
        f.write("\n")
    print(f"Saved {scene_path}")
    return pygame.time.get_ticks()


# ── Overlay rendering ──────────────────────────────────────────────────────────

def draw_bands(overlay, surfaces):
    for name, sd in surfaces.items():
        col   = surface_color(name)
        a_col = (*col, 55)
        b_col = (*col, 210)

        if "depth_y_far" in sd:
            y0 = s(sd["depth_y_far"])
            y1 = s(sd["depth_y_near"])
            pygame.draw.rect(overlay, a_col, pygame.Rect(0, y0, W, max(1, y1 - y0)))
            pygame.draw.rect(overlay, b_col, pygame.Rect(0, y0, W, max(1, y1 - y0)), 2)
            for wp in sd.get("waypoints", []):
                pygame.draw.circle(overlay, (*col, 180), s(wp[0], wp[1]), 3)
        else:
            y_top  = s(sd["y"])
            x0, x1 = s(sd["x_min"]), s(sd["x_max"])
            band_h = max(4, s(3))
            pygame.draw.rect(overlay, a_col, pygame.Rect(x0, y_top, max(1, x1 - x0), band_h))
            pygame.draw.rect(overlay, b_col, pygame.Rect(x0, y_top, max(1, x1 - x0), band_h), 2)
            pygame.draw.line(overlay, b_col, (x0, y_top - s(3)), (x0, y_top + band_h + s(3)), 2)
            pygame.draw.line(overlay, b_col, (x1, y_top - s(3)), (x1, y_top + band_h + s(3)), 2)


def draw_transitions(screen, surfaces):
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
            if to not in surfaces:
                continue
            dst = surfaces[to]

            if via == "jump":
                from_x = tr.get("from_x", src_cx)
                land_x  = tr.get("land_x", src_cx)
                land_y  = tr.get("land_y", surface_center_y(dst))
                draw_jump_arc(screen, JUMP_COLOR, s(from_x, src_y), s(land_x, land_y))

            elif via == "offscreen":
                exit_side = tr.get("exit_side", "right")
                entry_x   = tr.get("entry_x", src_cx)
                entry_y   = tr.get("entry_y", surface_center_y(dst))
                dst_col   = surface_color(to)

                edge_x = 0 if exit_side == "left" else W
                draw_dashed_line(screen, OFFSCREEN_COLOR,
                                 s(src_cx, src_y), (edge_x, s(src_y)))
                draw_arrowhead(screen, OFFSCREEN_COLOR,
                               (edge_x, s(src_y)), s(src_cx, src_y))

                entry_edge = s(3) if exit_side == "left" else W - s(3)
                draw_dashed_line(screen, dst_col,
                                 (entry_edge, s(entry_y)), s(entry_x, entry_y))
                draw_arrowhead(screen, dst_col,
                               s(entry_x, entry_y), (entry_edge, s(entry_y)))


def draw_handles(screen, handles, hovered_key, selected_wp):
    for kind, pos, surface_name, idx in handles:
        col = handle_color(kind, surface_name)
        dx, dy = s(pos[0]), s(pos[1])
        rect = pygame.Rect(dx - 3, dy - 3, 6, 6)
        pygame.draw.rect(screen, col, rect)
        pygame.draw.rect(screen, (0, 0, 0), rect, 1)
        key = (kind, surface_name, idx)
        if key == hovered_key:
            pygame.draw.rect(screen, (255, 220, 0), rect.inflate(4, 4), 2)
        elif kind == "waypoint" and selected_wp == (surface_name, idx):
            pygame.draw.rect(screen, (255, 255, 255), rect.inflate(4, 4), 2)


def draw_saved_indicator(screen, saved_at):
    if saved_at is None:
        return
    age = pygame.time.get_ticks() - saved_at
    if age > 1500:
        return
    alpha = max(0, 255 - int(age * 255 / 1500))
    ind = pygame.Surface((30, 12), pygame.SRCALPHA)
    ind.fill((60, 200, 60, alpha))
    screen.blit(ind, (W - 34, 4))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    argc = len(sys.argv)
    if argc > 1:
        scene_dir = os.path.normpath(sys.argv[1])
    else:
        scene_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "scenes", "city"))
    entity_id = sys.argv[2] if argc > 2 else None

    scene_path = os.path.join(scene_dir, "scene.json")
    with open(scene_path) as f:
        scene_data = json.load(f)

    editable = collect_editable_layers(scene_data)
    if not editable:
        print(f"No layers with 'surfaces' found in {scene_path}")
        return

    if entity_id:
        matches = [i for i, l in enumerate(editable) if l["id"] == entity_id]
        current_idx = matches[0] if matches else 0
    else:
        current_idx = 0

    def current_layer():
        return editable[current_idx]

    def print_entity_info():
        layer    = current_layer()
        surfaces = layer["surfaces"]
        print(f"\n── Entity: {layer['id']}  ({len(surfaces)} surfaces) ──────────────────")
        for name, sd in surfaces.items():
            col = surface_color(name)
            if "depth_y_far" in sd:
                print(f"  {name:<18} depth y={sd['depth_y_far']}–{sd['depth_y_near']}"
                      f"  waypoints={len(sd.get('waypoints', []))}  color=rgb{col}")
            else:
                print(f"  {name:<18} y={sd['y']}  x={sd['x_min']}–{sd['x_max']}"
                      f"  persp={sd.get('persp','?')}  color=rgb{col}")
        print()
        for name, sd in surfaces.items():
            for tr in sd.get("transitions", []):
                if tr["via"] == "jump":
                    print(f"  {name} --jump--> {tr['to']}  "
                          f"from_x={tr.get('from_x','?')} "
                          f"land={tr.get('land_x','?')},{tr.get('land_y','?')}")
                else:
                    print(f"  {name} --offscreen--> {tr['to']}  "
                          f"exit={tr.get('exit_side','?')} "
                          f"entry={tr.get('entry_x','?')},{tr.get('entry_y','?')}")
        print()

    def update_caption():
        layer = current_layer()
        pygame.display.set_caption(
            f"scene_editor — {os.path.basename(scene_dir)} — {layer['id']}"
            f"  [{current_idx + 1}/{len(editable)}]"
            f"  Tab=next  S=save  Del=rm-wp  SPACE=bg  ESC=quit"
        )

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    update_caption()

    print_entity_info()
    print("Loading scene background…")
    bg = None
    try:
        bg = render_scene_background(scene_dir)
        print(f"Background ready ({bg.get_size()}).")
    except Exception:
        import traceback
        traceback.print_exc()
        print("Could not render background — using plain fill. See traceback above.")

    show_bg      = True
    clock        = pygame.time.Clock()
    running      = True
    hovered_key  = None    # (kind, surface_name, idx)
    dragging     = None    # (kind, surface_name, idx)
    selected_wp  = None    # (surface_name, idx) — for keyboard delete
    saved_at     = None    # pygame ticks of last save
    backup_state = {"done": False}

    while running:
        layer    = current_layer()
        surfaces = layer["surfaces"]
        handles  = build_handles(layer)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    show_bg = not show_bg
                elif event.key == pygame.K_s:
                    saved_at = save_scene(scene_data, scene_path, backup_state)
                elif event.key == pygame.K_TAB:
                    step = -1 if (event.mod & pygame.KMOD_SHIFT) else 1
                    current_idx = (current_idx + step) % len(editable)
                    dragging = selected_wp = None
                    update_caption()
                    print_entity_info()
                elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                    if selected_wp is not None:
                        sname, widx = selected_wp
                        wps = surfaces.get(sname, {}).get("waypoints")
                        if wps is not None and 0 <= widx < len(wps):
                            wps.pop(widx)
                        selected_wp = None

            elif event.type == pygame.MOUSEBUTTONDOWN:
                emx, emy = event.pos
                esx, esy = unscale(emx, emy)
                if event.button == 1:
                    hit = hit_test(handles, emx, emy)
                    if hit:
                        dragging = hit
                        if hit[0] == "waypoint":
                            selected_wp = (hit[1], hit[2])
                        else:
                            selected_wp = None
                    else:
                        selected_wp = None
                        for name, sd in surfaces.items():
                            if "depth_y_far" in sd and "waypoints" in sd:
                                y0, y1 = sd["depth_y_far"], sd["depth_y_near"]
                                if y0 - 2 <= esy <= y1 + 2:
                                    sd["waypoints"].append([round(esx), round(esy)])
                                    break
                elif event.button == 3:
                    hit = hit_test(handles, emx, emy)
                    if hit and hit[0] == "waypoint":
                        sname, widx = hit[1], hit[2]
                        wps = surfaces.get(sname, {}).get("waypoints")
                        if wps is not None and 0 <= widx < len(wps):
                            wps.pop(widx)
                            if selected_wp == (sname, widx):
                                selected_wp = None

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    dragging = None

            elif event.type == pygame.MOUSEMOTION:
                if dragging is not None:
                    emx, emy = event.pos
                    esx, esy = unscale(emx, emy)
                    apply_drag(dragging, esx, esy, surfaces)

        mx, my = pygame.mouse.get_pos()
        hovered_key = hit_test(handles, mx, my)

        if show_bg and bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((18, 32, 85))
            if bg is None:
                # Draw a visible indicator so it's obvious the background failed
                pygame.draw.rect(screen, (180, 0, 0), pygame.Rect(0, 0, W, 8))

        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        draw_bands(overlay, surfaces)
        screen.blit(overlay, (0, 0))

        draw_transitions(screen, surfaces)

        # rebuild handles after any edits this frame so positions are current
        handles = build_handles(layer)
        draw_handles(screen, handles, hovered_key, selected_wp)
        draw_saved_indicator(screen, saved_at)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
