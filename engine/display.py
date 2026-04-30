import logging
import mmap

import numpy as np
import pygame

import config

logger = logging.getLogger(__name__)


class Display:
    """Abstracts Pi framebuffer vs desktop SDL window so the renderer never cares."""

    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)

        if config.DISPLAY_DRIVER == "sdl":
            self.screen = pygame.display.set_mode(
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )
            pygame.display.set_caption("pixel-pi")
            self._flip = self._flip_sdl

        elif config.DISPLAY_DRIVER == "fb":
            pygame.display.set_mode((1, 1), pygame.NOFRAME)
            self.screen = pygame.Surface(
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )
            fb_bytes = config.DISPLAY_WIDTH * config.DISPLAY_HEIGHT * 4
            self._fb = open(config.FRAMEBUFFER, "rb+")
            self._fb_map = mmap.mmap(
                self._fb.fileno(),
                fb_bytes,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
            )
            logger.info("Framebuffer opened: %s (%d bytes)", config.FRAMEBUFFER, fb_bytes)
            self._fill_fb_sky()
            self._flip = self._flip_fb

        else:
            raise ValueError(
                f"Unknown DISPLAY_DRIVER: {config.DISPLAY_DRIVER!r}. Use 'fb' or 'sdl'."
            )

    def flip(self):
        self._flip()

    def _fill_fb_sky(self):
        n = config.DISPLAY_WIDTH * config.DISPLAY_HEIGHT
        sky = np.zeros((n, 4), dtype=np.uint8)
        sky[:, 0] = 185  # B  (scene sky ≈ RGB 55,116,185)
        sky[:, 1] = 116  # G
        sky[:, 2] = 55   # R
        self._fb_map.seek(0)
        self._fb_map.write(sky.tobytes())

    def _flip_sdl(self):
        pygame.display.flip()

    def _flip_fb(self):
        raw = pygame.image.tostring(self.screen, 'RGB')
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        bgr = np.zeros((arr.shape[0], 4), dtype=np.uint8)
        bgr[:, 0] = arr[:, 2]  # B
        bgr[:, 1] = arr[:, 1]  # G
        bgr[:, 2] = arr[:, 0]  # R
        self._fb_map.seek(0)
        self._fb_map.write(bgr.tobytes())

    def close(self):
        if hasattr(self, "_fb_map"):
            self._fb_map.close()
            self._fb.close()
