import logging
import os
import queue
import random
from typing import Any, Dict, List, Optional

import pygame

import config
from engine.display import Display
from engine.queue_handler import QueueHandler
from engine.scene import Scene

logger = logging.getLogger(__name__)


class MovingSprite:
    """A one-shot sprite animation that optionally moves across the screen."""

    def __init__(self, surface: pygame.Surface, frame_w: int, frame_h: int,
                 x: float, y: float, fps: int, frame_count: int,
                 move_to_x: Optional[float], move_to_y: Optional[float],
                 speed: float):
        self.surface = surface
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.x = x
        self.y = y
        self.fps = max(fps, 1)
        self.frame_count = frame_count
        self.frame_duration = 1.0 / self.fps
        self.current_frame = 0
        self.elapsed = 0.0
        self.done = False

        self.move_to_x = move_to_x
        self.move_to_y = move_to_y
        self.speed = speed  # pixels per frame at TARGET_FPS

        # Determine if movement is involved
        self._moving = move_to_x is not None or move_to_y is not None

    def update(self, dt: float):
        if self.done:
            return

        self.elapsed += dt
        while self.elapsed >= self.frame_duration:
            self.elapsed -= self.frame_duration
            self.current_frame += 1
            if self.current_frame >= self.frame_count and not self._moving:
                self.done = True
                return

        if self._moving:
            tx = self.move_to_x if self.move_to_x is not None else self.x
            ty = self.move_to_y if self.move_to_y is not None else self.y
            dx = tx - self.x
            dy = ty - self.y
            dist = (dx**2 + dy**2) ** 0.5
            if dist < 1.0:
                self.x, self.y = tx, ty
                # Finish once we've also played through the animation
                if self.current_frame >= self.frame_count:
                    self.done = True
            else:
                move = self.speed * dt * config.TARGET_FPS
                ratio = min(move / dist, 1.0)
                self.x += dx * ratio
                self.y += dy * ratio

        # Loop frame while moving
        if self._moving:
            self.current_frame %= self.frame_count

    def draw(self, surface: pygame.Surface):
        if self.done or self.surface is None:
            return
        frame_idx = self.current_frame % self.frame_count
        src = pygame.Rect(frame_idx * self.frame_w, 0, self.frame_w, self.frame_h)
        surface.blit(self.surface, (int(self.x), int(self.y)), src)


class Renderer:
    def __init__(self, event_queue: queue.Queue):
        self._event_queue = event_queue
        self._scene: Optional[Scene] = None
        self._queue_handler: Optional[QueueHandler] = None
        self._display: Optional[Display] = None

        # Sequence state
        self._processing_sequence = False
        self._sequence: List[Dict[str, Any]] = []
        self._sequence_index = 0
        self._pending_events: List[str] = []

        # Per-action visual state
        self._current_sprite: Optional[MovingSprite] = None

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

        # Surfaces and timing
        self._render_surface: Optional[pygame.Surface] = None
        self._scaled_surface: Optional[pygame.Surface] = None
        self._font_surface: Optional[pygame.Surface] = None  # FONT sprite sheet
        self._clock: Optional[pygame.time.Clock] = None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _init_display(self):
        self._display = Display()
        self._render_surface = pygame.Surface((config.RENDER_WIDTH, config.RENDER_HEIGHT))
        self._scaled_surface = pygame.Surface((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
        self._clock = pygame.time.Clock()
        self._load_font()

    def _load_font(self):
        try:
            from engine.sprite_loader import get_surface
            self._font_surface = get_surface("FONT")
        except Exception as e:
            logger.warning("Could not load FONT sprite: %s", e)

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
            if self._display:
                self._display.close()
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
                layers = action.get("layers", [])
                self._scene.pause_layers(layers)
            return True

        elif kind == "resume_ambient":
            if self._scene:
                layers = action.get("layers", [])
                self._scene.resume_layers(layers)
            return True

        elif kind == "play_sprite":
            sprite_key = action.get("sprite_key")
            if sprite_key:
                self._start_sprite_from_key(action, sprite_key)
            else:
                # Legacy file-based path
                import sprites as sp
                path = os.path.join("assets", "sprites", action.get("sprite", ""))
                try:
                    surf = pygame.image.load(path).convert_alpha()
                    frames = action.get("frames", 1)
                    fw = surf.get_width() // frames
                    fh = surf.get_height()
                    self._current_sprite = MovingSprite(
                        surf, fw, fh,
                        float(action.get("x", 0)), float(action.get("y", 0)),
                        action.get("fps", 10), frames,
                        action.get("move_to_x"), action.get("move_to_y"),
                        action.get("speed", 1.0),
                    )
                except Exception as e:
                    logger.warning("Could not load legacy sprite %s: %s", path, e)
                    return True
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

    def _start_sprite_from_key(self, action: Dict[str, Any], key: str):
        import sprites as sp
        from engine.sprite_loader import get_surface
        try:
            surf = get_surface(key)
            w = getattr(sp, f"{key}_W")
            h = getattr(sp, f"{key}_H")
            frames = getattr(sp, f"{key}_FRAMES", 1)
            self._current_sprite = MovingSprite(
                surf, w, h,
                float(action.get("x", 0)), float(action.get("y", 0)),
                action.get("fps", 10), frames,
                action.get("move_to_x"), action.get("move_to_y"),
                action.get("speed", 1.0),
            )
        except Exception as e:
            logger.warning("Could not load sprite_key %s: %s", key, e)

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
        if not self._render_surface or not self._display:
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
            self._draw_flash_text(self._flash_text)

        pygame.transform.scale(
            self._render_surface,
            (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT),
            self._scaled_surface,
        )

        shake_x, shake_y = 0, 0
        if self._shake_intensity > 0:
            shake_x = random.randint(-self._shake_intensity, self._shake_intensity)
            shake_y = random.randint(-self._shake_intensity, self._shake_intensity)

        self._display.screen.fill((0, 0, 0))
        self._display.screen.blit(
            self._scaled_surface, (shake_x * config.SCALE, shake_y * config.SCALE)
        )
        self._display.flip()

    def _draw_flash_text(self, text: str):
        """Render text using the FONT sprite sheet, centered at x=120, y=18."""
        import sprites as sp

        char_w, char_h = sp.FONT_W, sp.FONT_H
        first = sp.FONT_FIRST_CHAR

        if self._font_surface is None:
            # Fallback: render nothing (font not loaded)
            return

        text_w = len(text) * char_w
        tx = (config.RENDER_WIDTH - text_w) // 2
        ty = 18

        # Draw backing
        backing = pygame.Surface((text_w + 6, char_h + 4), pygame.SRCALPHA)
        backing.fill((0, 0, 0, 160))
        self._render_surface.blit(backing, (tx - 3, ty - 2))

        for i, ch in enumerate(text):
            code = ord(ch)
            if code < first or code >= first + sp.FONT_FRAMES:
                continue
            frame = code - first
            src = pygame.Rect(frame * char_w, 0, char_w, char_h)
            # Shadow pass at +1,+1 in dark color
            shadow_surf = pygame.Surface((char_w, char_h), pygame.SRCALPHA)
            shadow_surf.blit(self._font_surface, (0, 0), src)
            # Tint to dark
            dark = pygame.Surface((char_w, char_h), pygame.SRCALPHA)
            dark.fill((13, 8, 4, 255))
            shadow_surf.blit(dark, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._render_surface.blit(shadow_surf, (tx + i * char_w + 1, ty + 1))
            # White pass
            white_surf = pygame.Surface((char_w, char_h), pygame.SRCALPHA)
            white_surf.blit(self._font_surface, (0, 0), src)
            self._render_surface.blit(white_surf, (tx + i * char_w, ty))
