import pygame
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SpriteAnimation:
    def __init__(self, sprite_path: str, x: int, y: int, frame_count: int, fps: int):
        self.x = x
        self.y = y
        self.frame_count = frame_count
        self.frame_duration = 1.0 / max(fps, 1)
        self.current_frame = 0
        self.elapsed = 0.0
        self.done = False
        self.surface: Optional[pygame.Surface] = None
        self.frame_width = 0
        self.frame_height = 0

        try:
            raw = pygame.image.load(sprite_path).convert_alpha()
            self.surface = raw
            self.frame_width = raw.get_width() // frame_count
            self.frame_height = raw.get_height()
        except Exception as e:
            logger.warning("Could not load sprite %s: %s", sprite_path, e)
            self.done = True

    def update(self, dt: float):
        if self.done:
            return
        self.elapsed += dt
        while self.elapsed >= self.frame_duration:
            self.elapsed -= self.frame_duration
            self.current_frame += 1
            if self.current_frame >= self.frame_count:
                self.done = True
                return

    def draw(self, surface: pygame.Surface):
        if self.done or self.surface is None:
            return
        src = pygame.Rect(
            self.current_frame * self.frame_width, 0,
            self.frame_width, self.frame_height,
        )
        surface.blit(self.surface, (self.x, self.y), src)
