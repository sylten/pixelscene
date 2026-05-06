"""
city_sprite_converter.py

Converts CP_V1.1.0_nyknck reference sprites into palette-indexed arrays for sprites.py.

Usage:
    python3 tools/city_sprite_converter.py --analyze     # print exact frame positions
    python3 tools/city_sprite_converter.py --preview     # save PNG crops to /tmp/city_preview/
    python3 tools/city_sprite_converter.py --generate    # print Python code for sprites.py
    python3 tools/city_sprite_converter.py --generate --sprites building_red,lamp_corner

Requirements: Pillow  (pip install Pillow)
"""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow not found. Run: pip install Pillow")

REF_DIR = Path("/Users/jonas/Dev/pixelscene/references/CP_V1.1.0_nyknck")
BL001   = REF_DIR / "Animations/BL001.png"
BD001   = REF_DIR / "Animations/BD001.png"
SL001   = REF_DIR / "Animations/SL001.png"

# Existing PAL ends at index 72; city colors start here
CITY_PAL_START = 73


# ── Sprite definitions (explicit per-frame bounding boxes) ─────────────────────
# Format: name -> (source_path, [(x0,y0,x1,y1), ...])
# Each tuple is one frame's crop rectangle (exclusive x1+1, y1+1).
# Frames within a sprite are padded to the same width (widest frame wins).
#
# BL001 frame layout: col[0]=day/unlit, col[1]=night/lit
# BD001 frame layout: col[0]=off, col[1]=dim, col[2]=bright (3 lighting states)
# SL001 lamp layout varies; see --analyze output for exact coords

SPRITE_DEFS = {
    # ── Buildings from BL001 (2 frames: day=0, night=1) ───────────────────────
    "building_red": (BL001, [
        (48, 32, 96, 128),    # day
        (128, 32, 176, 128),  # night (lit windows)
    ]),
    "building_blue": (BL001, [
        (48, 176, 96, 272),
        (128, 176, 176, 272),
    ]),
    "building_tower": (BL001, [
        (48, 304, 96, 400),
        (128, 304, 176, 400),
    ]),
    "building_skyscraper": (BL001, [
        (48, 432, 128, 528),   # 80px wide
        (144, 432, 224, 528),
    ]),
    "building_storefront_green": (BL001, [
        (48, 598, 112, 640),   # 64px wide
        (144, 598, 208, 640),
    ]),
    "building_storefront_gray": (BL001, [
        (48, 688, 112, 736),
        (161, 688, 225, 736),
    ]),
    "building_shoe": (BL001, [
        (48, 783, 96, 832),
        (161, 783, 209, 832),
    ]),
    "building_bar": (BL001, [
        (49, 874, 113, 928),
        (161, 874, 225, 928),
    ]),
    "building_market": (BL001, [
        (49, 960, 97, 1008),
        (161, 960, 209, 1008),
    ]),
    "building_shop_orange": (BL001, [
        (49, 1061, 97, 1104),
        (161, 1061, 209, 1104),
    ]),
    "building_door_gray": (BL001, [
        (49, 1152, 81, 1200),   # 32px wide
        (161, 1152, 193, 1200),
    ]),
    "building_shop_blue": (BL001, [
        (49, 1232, 97, 1328),
        (161, 1232, 209, 1328),
    ]),

    # ── Buildings from BD001 (3 frames: off=0, dim=1, bright=2) ───────────────
    "bd_storefront": (BD001, [
        (32, 22, 96, 64),    # 64px wide, off
        (144, 22, 208, 64),  # dim
        (256, 22, 320, 64),  # bright
    ]),
    "bd_apartment": (BD001, [
        (48, 608, 96, 704),   # 48px wide
        (128, 608, 176, 704),
        (208, 608, 256, 704),
    ]),
    "bd_office": (BD001, [
        (48, 752, 96, 848),
        (128, 752, 176, 848),
        (208, 752, 256, 848),
    ]),
    "bd_warehouse": (BD001, [
        (32, 880, 112, 976),  # 80px wide
        (145, 880, 225, 976),
        (258, 880, 338, 976),
    ]),

    # ── Street lamps from SL001 ────────────────────────────────────────────────
    # row[6] y=368-399: straight lamp (off=9px, lit=31px) — pad to 31px
    "lamp_straight": (SL001, [
        (32, 368, 41, 400),   # off (9px, padded to 31)
        (53, 368, 84, 400),   # lit (31px)
    ]),
    # row[7] y=416-447: corner lamp (24px off, 36px lit, 24px off-variant) — pad to 36px
    "lamp_corner": (SL001, [
        (32, 416, 56, 448),   # off (24px)
        (64, 416, 100, 448),  # lit (36px)
    ]),
    # row[8] y=464-495: small globe lamp (9px, 31px, 9px) — 2 frames (off + lit)
    "lamp_globe": (SL001, [
        (32, 464, 41, 496),   # off (9px)
        (53, 464, 84, 496),   # lit (31px)
    ]),
    # row[9] y=513-543: wide globe lamp (9px, 33px, 9px)
    "lamp_globe_wide": (SL001, [
        (32, 513, 41, 544),   # off
        (52, 513, 85, 544),   # lit
    ]),

    # ── Traffic lights from SL001 ──────────────────────────────────────────────
    # row[0]: 4 tiny traffic light heads (8px each), treat as 4-frame animation
    "traffic_light_head": (SL001, [
        (31, 34, 39, 64),
        (63, 34, 71, 64),
        (95, 34, 103, 64),
        (127, 34, 135, 64),
    ]),
    # row[1]: 4 corner traffic lights (29px each)
    "traffic_light_corner": (SL001, [
        (32, 80, 61, 112),
        (80, 80, 109, 112),
        (128, 80, 157, 112),
        (176, 80, 205, 112),
    ]),
}


# ── Extraction ─────────────────────────────────────────────────────────────────

def extract_sprite(name, path, frame_boxes):
    """
    Crop each frame from the source image.
    Returns (frames: list[PIL.Image], frame_w: int, frame_h: int).
    Frames are padded with transparency to the same dimensions.
    """
    img = Image.open(path).convert("RGBA")
    crops = [img.crop((x0, y0, x1, y1)) for (x0, y0, x1, y1) in frame_boxes]

    frame_w = max(c.width for c in crops)
    frame_h = max(c.height for c in crops)

    padded = []
    for c in crops:
        if c.size == (frame_w, frame_h):
            padded.append(c)
        else:
            canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
            # center horizontally, align bottom
            x_off = (frame_w - c.width) // 2
            y_off = frame_h - c.height
            canvas.paste(c, (x_off, y_off))
            padded.append(canvas)

    return padded, frame_w, frame_h


# ── Color quantization ─────────────────────────────────────────────────────────

def load_existing_pal(sprites_py_path):
    """Parse PAL dict from sprites.py. Returns {idx: (r,g,b,a)}."""
    import ast
    try:
        src = Path(sprites_py_path).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "PAL":
                        pal = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            idx = ast.literal_eval(k)
                            rgba = tuple(ast.literal_eval(v))
                            pal[idx] = rgba
                        return pal
    except Exception as e:
        print(f"Warning: could not parse sprites.py PAL: {e}", file=sys.stderr)
    return {}


def build_color_map(frames_list, existing_pal, start_idx):
    """
    Collect unique opaque colors from all frames.
    Map each to an existing PAL index if close enough (exact match only),
    otherwise assign a new index starting at start_idx.
    Returns (color_to_idx, new_entries).
    """
    existing_rev = {rgba: idx for idx, rgba in existing_pal.items()}
    colors = set()
    for frames in frames_list:
        for frame in frames:
            for px in frame.getdata():
                r, g, b, a = px
                if a > 10:
                    colors.add((r, g, b, 255))  # normalise alpha

    color_to_idx = {}
    new_entries = {}
    next_idx = start_idx

    for color in sorted(colors):
        if color in existing_rev:
            color_to_idx[color] = existing_rev[color]
        else:
            color_to_idx[color] = next_idx
            new_entries[next_idx] = color
            next_idx += 1

    return color_to_idx, new_entries


def image_to_indices(img, color_to_idx):
    """Convert RGBA image to flat list of palette indices."""
    result = []
    for r, g, b, a in img.getdata():
        if a <= 10:
            result.append(0)
        else:
            key = (r, g, b, 255)
            result.append(color_to_idx.get(key, 0))
    return result


# ── Output formatting ──────────────────────────────────────────────────────────

def format_sprite_code(name, indices, frame_w, frame_h, num_frames):
    varname = f"CITY_{name.upper()}"
    lines = [
        f"# {varname}: {frame_w}x{frame_h} px, {num_frames} frame(s)  "
        f"(frame 0 = day/off, frame 1 = night/lit)",
        f"{varname}_W, {varname}_H, {varname}_FRAMES = {frame_w}, {frame_h}, {num_frames}",
        f"{varname} = [",
    ]
    stride = frame_w
    for row_start in range(0, len(indices), stride):
        row = indices[row_start:row_start + stride]
        lines.append("    " + ",".join(map(str, row)) + ",")
    lines.append("]")
    return "\n".join(lines)


def format_pal_entries(new_entries):
    if not new_entries:
        return "    # (no new palette entries needed)"
    lines = []
    for idx in sorted(new_entries):
        r, g, b, a = new_entries[idx]
        lines.append(f"    {idx}: ({r:3d}, {g:3d}, {b:3d}, {a}),")
    return "\n".join(lines)


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_analyze():
    for label, path in [("BL001", BL001), ("BD001", BD001), ("SL001", SL001)]:
        img = Image.open(path).convert("RGBA")
        data = img.load()
        w, h = img.size
        print(f"\n{'='*60}")
        print(f"{label} ({w}x{h})  — per-row frame positions")

        # Find row spans
        row_spans = []
        in_row = False
        for y in range(h):
            empty = all(data[x, y][3] <= 10 for x in range(w))
            if not empty and not in_row:
                row_spans.append([y, y])
                in_row = True
            elif not empty and in_row:
                row_spans[-1][1] = y
            elif empty and in_row:
                in_row = False

        for ri, (y0, y1) in enumerate(row_spans):
            col_spans = []
            in_col = False
            for x in range(w):
                empty = all(data[x, y][3] <= 10 for y in range(y0, y1 + 1))
                if not empty and not in_col:
                    col_spans.append([x, x])
                    in_col = True
                elif not empty and in_col:
                    col_spans[-1][1] = x
                elif empty and in_col:
                    in_col = False
            span_str = "  ".join(
                f"[{i}] x={x0}-{x1} w={x1-x0+1}" for i, (x0, x1) in enumerate(col_spans)
            )
            print(f"  row[{ri:2d}] y={y0}-{y1} h={y1-y0+1}  cols: {span_str}")


def cmd_preview(sprite_filter=None):
    out_dir = Path("/tmp/city_preview")
    out_dir.mkdir(exist_ok=True)

    for name, (path, boxes) in SPRITE_DEFS.items():
        if sprite_filter and name not in sprite_filter:
            continue
        try:
            frames, fw, fh = extract_sprite(name, path, boxes)
        except Exception as e:
            print(f"  SKIP {name}: {e}")
            continue

        sheet = Image.new("RGBA", (fw * len(frames), fh), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            sheet.paste(f, (i * fw, 0))
        out = out_dir / f"{name}.png"
        sheet.save(out)
        print(f"  {name}: {fw}x{fh} x{len(frames)}f  -> {out}")

    print(f"\nOpen previews: open /tmp/city_preview/")


def cmd_generate(sprite_filter=None):
    sprites_py = Path(__file__).parent.parent / "sprites.py"
    existing_pal = load_existing_pal(sprites_py)

    selected = {
        name: (path, boxes)
        for name, (path, boxes) in SPRITE_DEFS.items()
        if not sprite_filter or name in sprite_filter
    }

    all_frame_lists = []
    sprite_data = {}
    for name, (path, boxes) in selected.items():
        try:
            frames, fw, fh = extract_sprite(name, path, boxes)
            all_frame_lists.append(frames)
            sprite_data[name] = (frames, fw, fh)
            print(f"  Extracted {name}: {fw}x{fh} x{len(frames)}f", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {name}: {e}", file=sys.stderr)

    color_to_idx, new_entries = build_color_map(all_frame_lists, existing_pal, CITY_PAL_START)

    print("# " + "="*72)
    print("# CITY PALETTE EXTENSION")
    print("# Add these entries to the PAL dict in sprites.py")
    print("# " + "="*72)
    print("PAL.update({")
    print(format_pal_entries(new_entries))
    print("})")

    print()
    print("# " + "="*72)
    print("# CITY SPRITES — paste at bottom of sprites.py")
    print("# " + "="*72)

    for name, (frames, fw, fh) in sprite_data.items():
        combined = []
        for frame in frames:
            combined.extend(image_to_indices(frame, color_to_idx))
        print()
        print(format_sprite_code(name, combined, fw, fh, len(frames)))

    total_new = len(new_entries)
    total_pix = sum(fw * fh * len(frames) for _, (frames, fw, fh) in sprite_data.items())
    print(f"\n# Summary: {len(sprite_data)} sprites, {total_new} new palette entries, "
          f"{total_pix} total pixels", file=sys.stderr)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze",  action="store_true")
    parser.add_argument("--preview",  action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--sprites",  type=str, default=None,
                        help="Comma-separated sprite names (default: all)")
    args = parser.parse_args()

    sprite_filter = set(args.sprites.split(",")) if args.sprites else None

    if args.analyze:
        cmd_analyze()
    elif args.preview:
        cmd_preview(sprite_filter)
    elif args.generate:
        cmd_generate(sprite_filter)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
