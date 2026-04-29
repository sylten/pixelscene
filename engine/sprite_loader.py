"""Load sprites from sprites.py pixel arrays, cached after first load."""
import pygame
import sprites

_cache: dict = {}


def get_surface(key: str) -> pygame.Surface:
    if key in _cache:
        return _cache[key]
    data = getattr(sprites, key)
    w = getattr(sprites, f"{key}_W")
    h = getattr(sprites, f"{key}_H")
    surface = sprites.make_surface(data, sprites.PAL, w, h)
    _cache[key] = surface
    return surface
