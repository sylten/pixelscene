import logging
import mmap
import os
import queue
import random
from typing import Any, Dict, List, Optional

import pygame

import config
from engine.animation import SpriteAnimation
from engine.queue_handler import QueueHandler
from engine.scene import Scene

logger = logging.getLogger(__name__)


class Renderer:
    def __init__(self, event_queue: queue.Queue):
        self._event_queue = event_queue
        self._scene: Optional[Scene] = None
        self._queue_handler: Optional[QueueHandler] = None

        # Sequence state
        self._processing_sequence = False
        self._sequence: List[Dict[str, Any]] = []
        self._sequence_index = 0
        self._pending_events: List[str] = []

        # Per-action visual state
        self._current_sprite: Optional[SpriteAnimation] = None

        self._flash_text: Optional[str] = None
        self._flash_text_elapsed = 0.0
        self._flash_text_duration = 0.0

        self._flash_color: Optional[tuple] = None
        self._flash_timer = 0.0
        self._flash_duration = 0.0

        self._shake_intensity = 0
        self._shake_elapsed = 0.0
        self._shake_duration = 0.0

        self._tint_color: Optional[tuple] = None
        self._tint_alpha = 0
        self._tint_timer = 0.0
        self._tint_duration = 0.0

        # pygame surfaces / objects
        self._render_surface: Optional[pygame.Surface] = None
        self._display_surface: Optional[pygame.Surface] = None
        self._font: Optional[pygame.font.Font] = None
        self._clock: Optional[pygame.time.Clock] = None

        # Framebuffer resources (fb mode only)
        self._fb_file = None
        self._fb_map: Optional[mmap.mmap] = None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _init_display(self):
        pygame.init()
        pygame.font.init()

        if config.DISPLAY_DRIVER == "fb":
            # Direct framebuffer — no SDL display window.
            # pygame draws to an offscreen Surface; we mmap-write frames to /dev/fb0.
            # This is required on Bookworm where SDL 2 ships without fbcon support.
            self._display_surface = pygame.Surface(
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )
            fb_bytes = config.DISPLAY_WIDTH * config.DISPLAY_HEIGHT * 4
            self._fb_file = open(config.FRAMEBUFFER, "rb+")
            self._fb_map = mmap.mmap(
                self._fb_file.fileno(),
                fb_bytes,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
            )
            logger.info("Framebuffer opened: %s (%d bytes)", config.FRAMEBUFFER, fb_bytes)

        elif config.DISPLAY_DRIVER == "sdl":
            self._display_surface = pygame.display.set_mode(
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )
            pygame.display.set_caption("pixel-pi")

        else:
            raise ValueError(f"Unknown DISPLAY_DRIVER: {config.DISPLAY_DRIVER!r}. Use 'fb' or 'sdl'.")

        self._render_surface = pygame.Surface((config.RENDER_WIDTH, config.RENDER_HEIGHT))
        self._clock = pygame.time.Clock()
        self._font = pygame.font.Font(None, 16)

    def _load_scene(self):
        scene_dir = os.path.join("scenes", config.DEFAULT_SCENE)
        self._scene = Scene(scene_dir)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self._init_display()
        self._load_scene()
        self._queue_handler = QueueHandler(self._event_queue, self._on_event_received)
        try:
            self._loop()
        finally:
            if self._fb_map:
                self._fb_map.close()
            if self._fb_file:
                self._fb_file.close()
            pygame.quit()

    def _loop(self):
        running = True
        while running:
            dt = self._clock.tick(config.TARGET_FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            if not self._processing_sequence:
                self._queue_handler.poll()

            self._update(dt)
            self._draw()

    # ------------------------------------------------------------------
    # Event / sequence management
    # ------------------------------------------------------------------

    def _on_event_received(self, event_name: str):
        if self._scene is None:
            return
        sequence = self._scene.get_event_sequence(event_name)
        if sequence is None:
            return
        if self._processing_sequence:
            self._pending_events.append(event_name)
            return
        self._start_sequence(sequence)

    def _start_sequence(self, sequence: List[Dict[str, Any]]):
        self._sequence = sequence
        self._sequence_index = 0
        self._processing_sequence = True
        self._current_sprite = None
        self._advance_sequence()

    def _advance_sequence(self):
        while self._sequence_index < len(self._sequence):
            action = self._sequence[self._sequence_index]
            self._sequence_index += 1
            done = self._execute_action(action)
            if not done:
                return

        self._processing_sequence = False

        if self._pending_events:
            next_event = self._pending_events.pop(0)
            if self._scene:
                sequence = self._scene.get_event_sequence(next_event)
                if sequence:
                    self._start_sequence(sequence)

    def _execute_action(self, action: Dict[str, Any]) -> bool:
        """Returns True when complete immediately, False when it takes time."""
        kind = action.get("action")

        if kind == "pause_ambient":
            if self._scene:
                self._scene.ambient_paused = True
            return True

        elif kind == "resume_ambient":
            if self._scene:
                self._scene.ambient_paused = False
            return True

        elif kind == "play_sprite":
            path = os.path.join("assets", "sprites", action.get("sprite", ""))
            self._current_sprite = SpriteAnimation(
                path,
                action.get("x", 0),
                action.get("y", 0),
                action.get("frames", 1),
                action.get("fps", 10),
            )
            return False

        elif kind == "flash_text":
            self._flash_text = action.get("text", "")
            self._flash_text_duration = action.get("duration_ms", 1000) / 1000.0
            self._flash_text_elapsed = 0.0
            return False

        elif kind == "screen_flash":
            self._flash_color = tuple(action.get("color", [255, 255, 255]))
            self._flash_duration = action.get("duration_ms", 100) / 1000.0
            self._flash_timer = 0.0
            return False

        elif kind == "screen_shake":
            self._shake_intensity = action.get("intensity", 3)
            self._shake_duration = action.get("duration_ms", 400) / 1000.0
            self._shake_elapsed = 0.0
            return False

        elif kind == "set_tint":
            self._tint_color = tuple(action.get("color", [255, 255, 255]))
            self._tint_alpha = action.get("alpha", 80)
            duration_ms = action.get("duration_ms", 0)
            if duration_ms > 0:
                self._tint_duration = duration_ms / 1000.0
                self._tint_timer = 0.0
                return False
            self._tint_duration = 0.0
            return True

        else:
            logger.warning("Unknown action type: %s", kind)
            return True

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def _update(self, dt: float):
        if self._scene:
            self._scene.update(dt)

        if not self._processing_sequence:
            return

        action_done = False

        if self._current_sprite is not None:
            self._current_sprite.update(dt)
            if self._current_sprite.done:
                self._current_sprite = None
                action_done = True

        elif self._flash_text is not None:
            self._flash_text_elapsed += dt
            if self._flash_text_elapsed >= self._flash_text_duration:
                self._flash_text = None
                action_done = True

        elif self._flash_color is not None:
            self._flash_timer += dt
            if self._flash_timer >= self._flash_duration:
                self._flash_color = None
                action_done = True

        elif self._shake_duration > 0.0:
            self._shake_elapsed += dt
            if self._shake_elapsed >= self._shake_duration:
                self._shake_intensity = 0
                self._shake_duration = 0.0
                action_done = True

        elif self._tint_color is not None and self._tint_duration > 0.0:
            self._tint_timer += dt
            if self._tint_timer >= self._tint_duration:
                self._tint_color = None
                action_done = True

        if action_done:
            self._advance_sequence()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw(self):
        if not self._render_surface or not self._display_surface:
            return

        if self._scene:
            self._scene.draw(self._render_surface)
        else:
            self._render_surface.fill((20, 20, 40))

        if self._current_sprite:
            self._current_sprite.draw(self._render_surface)

        if self._tint_color:
            overlay = pygame.Surface(
                (config.RENDER_WIDTH, config.RENDER_HEIGHT), pygame.SRCALPHA
            )
            overlay.fill((*self._tint_color, self._tint_alpha))
            self._render_surface.blit(overlay, (0, 0))

        if self._flash_color:
            progress = self._flash_timer / max(self._flash_duration, 0.001)
            alpha = int(255 * max(0.0, 1.0 - progress))
            overlay = pygame.Surface(
                (config.RENDER_WIDTH, config.RENDER_HEIGHT), pygame.SRCALPHA
            )
            overlay.fill((*self._flash_color, alpha))
            self._render_surface.blit(overlay, (0, 0))

        if self._flash_text:
            text_surf = self._font.render(self._flash_text, False, (255, 255, 180))
            tw, th = text_surf.get_size()
            tx = (config.RENDER_WIDTH - tw) // 2
            ty = (config.RENDER_HEIGHT - th) // 2
            backing = pygame.Surface((tw + 6, th + 4), pygame.SRCALPHA)
            backing.fill((0, 0, 0, 160))
            self._render_surface.blit(backing, (tx - 3, ty - 2))
            self._render_surface.blit(text_surf, (tx, ty))

        scaled = pygame.transform.scale(
            self._render_surface, (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
        )

        shake_x, shake_y = 0, 0
        if self._shake_intensity > 0:
            shake_x = random.randint(-self._shake_intensity, self._shake_intensity)
            shake_y = random.randint(-self._shake_intensity, self._shake_intensity)

        self._display_surface.fill((0, 0, 0))
        self._display_surface.blit(scaled, (shake_x * config.SCALE, shake_y * config.SCALE))

        if config.DISPLAY_DRIVER == "fb":
            raw = pygame.image.tostring(self._display_surface, "RGBX")
            self._fb_map.seek(0)
            self._fb_map.write(raw)
        else:
            pygame.display.flip()
