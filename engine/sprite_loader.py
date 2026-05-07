"""Load sprites from sprites.py pixel arrays, cached after first load."""
import pygame
import sprites

_cache: dict = {}

# Per-key post-load fixups applied once after the surface is built.
# Each entry is a callable (surface) -> None that patches pixels in-place.
def _fix_city_road(surf: pygame.Surface):
    """Remove the white lane-edge markings at x=0-1 and x=238-239."""
    road_color = sprites.PAL[107][:3] + (255,)
    w = surf.get_width()
    for y in range(6, surf.get_height()):
        for x in (0, 1, w - 2, w - 1):
            if surf.get_at((x, y))[:3] == sprites.PAL[113][:3]:
                surf.set_at((x, y), road_color)

_POST_PROCESS = {
    "CITY_ROAD": _fix_city_road,
}


def get_surface(key: str) -> pygame.Surface:
    if key in _cache:
        return _cache[key]
    data = getattr(sprites, key)
    w = getattr(sprites, f"{key}_W")
    h = getattr(sprites, f"{key}_H")
    surface = sprites.make_surface(data, sprites.PAL, w, h)
    if key in _POST_PROCESS:
        _POST_PROCESS[key](surface)
    _cache[key] = surface
    return surface
