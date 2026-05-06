# /new-scene — Create a new pixelscene scene from reference sprites

Use this skill when asked to create a new scene (background + layers + events) for the pixelscene engine.

---

## Engine quick-reference

| Constant | Value |
|---|---|
| Render size | 240 × 160 px |
| Display size | 480 × 320 px (2× scale) |
| Target FPS | 30 |
| Sprite store | `sprites.py` — palette-indexed arrays + `PAL` dict |

**Layer types** (defined in `engine/scene.py`):

| type | behaviour |
|---|---|
| `static` | blitted once per frame at (x, y), optional `sway` |
| `animated` | sprite sheet, cycles frames at `fps`; `fps: 0` = locked |
| `scroll` | tiles horizontally, moves left at `scroll_speed` px/frame |
| `firefly` | animated + sinusoidal drift via `drift: {period, phase, x, y}` |
| `character` | animated, walks between `waypoints` |

---

## Step 1 — Analyse the reference sprites

Open the reference images with Pillow and identify exact pixel bounding boxes for each sprite cell. Do **not** rely on auto-detection when buildings or objects have different widths per row — use explicit boxes.

```python
from PIL import Image
img = Image.open("path/to/sheet.png").convert("RGBA")
# Sample a known pixel to confirm coordinates
print(img.getpixel((x, y)))
```

Save `tools/<scene>_sprite_converter.py` with a `SPRITE_DEFS` dict:

```python
SPRITE_DEFS = {
    "MY_SPRITE": (PATH_TO_IMAGE, [(x0,y0,x1,y1), ...]),  # one box per frame
}
```

---

## Step 2 — Extract and convert to palette indices

For each sprite:
1. Crop each frame box from the source image
2. Pad all frames to uniform dimensions (max W × max H)
3. Collect unique RGBA colors; skip fully transparent pixels (alpha < 128) → index 0
4. Map each new color to the next available PAL index (current max + 1)
5. Emit the flat pixel-index list, row-major (left→right, top→bottom)

**Key rule:** Reuse existing PAL entries where colors match exactly — look up `reverse = {v: k for k, v in PAL.items()}` before allocating new indices.

The current PAL lives in `sprites.py`. City sprites start at index 73; extend from `max(PAL.keys()) + 1`.

---

## Step 3 — Append to sprites.py

Format:

```python
PAL.update({
    135: (18, 32, 85, 255),
    # ...
})

# MY_SPRITE: WxH, N frames (frame 0 = day/off, frame 1 = night/lit)
MY_SPRITE_W, MY_SPRITE_H, MY_SPRITE_FRAMES = W, H, N
MY_SPRITE = [
    idx, idx, idx, ...,   # row 0, frame 0 then frame 1 ...
    # one line per pixel row
]
```

Validate immediately:

```bash
python3 -c "import sprites; print(len(sprites.MY_SPRITE), sprites.MY_SPRITE_W * sprites.MY_SPRITE_H * sprites.MY_SPRITE_FRAMES)"
# both numbers must match
```

---

## Step 4 — Create scene files

**`scenes/<name>/scene.json`** — layer stack, drawn bottom to top:

```json
{
  "id": "<name>",
  "background_color": [R, G, B],
  "layers": [
    { "id": "sky",      "type": "static",   "sprite_key": "MY_SKY",    "x": 0, "y": 0 },
    { "id": "clouds",   "type": "scroll",   "sprite_key": "MY_CLOUDS", "scroll_speed": 0.3, "y": 4 },
    { "id": "building", "type": "animated", "sprite_key": "MY_BUILDING","fps": 0, "x": 0, "y": 34 },
    { "id": "road",     "type": "static",   "sprite_key": "MY_ROAD",   "x": 0, "y": 130 },
    { "id": "cars",     "type": "scroll",   "sprite_key": "MY_CARS",   "scroll_speed": 2.5, "y": 128 }
  ]
}
```

Tips:
- `fps: 0` on an `animated` layer = static until a `set_layer_frame` event changes it (day/night toggle pattern)
- `background_color` should match the darkest sky colour so it never shows as a seam
- Layer order matters — later entries draw on top

**`scenes/<name>/events.json`** — HTTP-triggered action sequences:

```json
{
  "night_fall": {
    "sequence": [
      { "action": "set_tint",        "color": [10, 10, 50], "alpha": 120 },
      { "action": "set_layer_frame", "layer": "building",   "frame": 1 },
      { "action": "set_layer_frame", "layer": "lamp",       "frame": 1 }
    ]
  },
  "sunrise": {
    "sequence": [
      { "action": "clear_tint" },
      { "action": "set_layer_frame", "layer": "building",   "frame": 0 },
      { "action": "set_layer_frame", "layer": "lamp",       "frame": 0 }
    ]
  }
}
```

Available actions: `set_tint`, `clear_tint`, `set_layer_frame`, `screen_flash`, `screen_shake`, `flash_text`, `play_sprite`, `pause_ambient`, `resume_ambient`.

---

## Step 5 — Verify with a render test

```python
import os; os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame; pygame.init(); pygame.display.set_mode((1,1))
import config; config.DEFAULT_SCENE = "<name>"
from engine.scene import Scene
from PIL import Image

scene = Scene("scenes/<name>")
surf = pygame.Surface((240, 160))
scene.draw(surf)
scaled = pygame.transform.scale(surf, (480, 320))
pygame.image.save(scaled, "/tmp/preview.bmp")
Image.open("/tmp/preview.bmp").save("/tmp/preview.png")
```

Read `/tmp/preview.png` to visually confirm layer positions and colours before running the full app.

---

## Known gotchas

- **CP_V1.0.4.png vehicles face LEFT** — do not apply `FLIP_LEFT_RIGHT`. The scroll layer moves left, so left-facing sprites drive correctly.
- **Sprite sheet auto-detection fails** when rows have different frame widths — always use explicit bounding boxes.
- **PAL index 0 = transparent** — never assign a visible colour to index 0.
- **`make_surface` uses numpy LUT** — pixel arrays must be flat, row-major (W × H × FRAMES values total).
- **Sky gradient** — use ~10 colour bands across the height; fully quantised gradients with 30+ unique colours bloat the PAL unnecessarily.
- **Scroll strips** should be wider than 240 px (e.g. 320–480) for natural gap variation between repeating elements.

---

## Triggering events at runtime

```bash
curl -X POST http://localhost:5000/event \
     -H "Content-Type: application/json" \
     -d '{"event": "night_fall"}'
```

The day/night scheduler in `main.py` fires `night_fall` at 17:00 and `sunrise` at 06:00 automatically.
