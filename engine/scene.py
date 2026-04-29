import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

import pygame

import config

logger = logging.getLogger(__name__)


class Layer:
    def __init__(self, layer_def: Dict[str, Any], elapsed: float = 0.0):
        self._def = layer_def
        self.id: str = layer_def.get("id", "")
        self.layer_type: str = layer_def.get("type", "static")
        self.surface: Optional[pygame.Surface] = None

        # Per-type mutable state
        self._scroll_offset = 0.0
        self._frame_index = 0
        self._frame_elapsed = 0.0
        self._walk_pos: Optional[List[float]] = None
        self._waypoint_index = 0

        # Shared scene elapsed time reference (set by Scene.update)
        self._elapsed = elapsed

        self._load_surface()

    def _load_surface(self):
        # Prefer sprite_key (load from sprites.py) over sprite (file path)
        key = self._def.get("sprite_key")
        if key:
            try:
                from engine.sprite_loader import get_surface
                self.surface = get_surface(key)
            except Exception as e:
                logger.warning("Layer %s: could not load sprite_key %s: %s", self.id, key, e)
            return

        path = self._def.get("sprite")
        if path and os.path.exists(path):
            try:
                self.surface = pygame.image.load(path).convert_alpha()
            except Exception as e:
                logger.warning("Layer %s: could not load %s: %s", self.id, path, e)

        if self.layer_type == "character":
            waypoints = self._def.get("waypoints", [])
            if waypoints:
                self._walk_pos = list(map(float, waypoints[0]))

    # ------------------------------------------------------------------
    def update(self, dt: float, paused: bool, elapsed: float):
        self._elapsed = elapsed
        if paused:
            return

        t = self.layer_type

        if t == "scroll":
            speed = self._def.get("scroll_speed", 0.2)
            self._scroll_offset += speed * dt * config.TARGET_FPS
            if self.surface:
                self._scroll_offset %= self.surface.get_width()

        elif t in ("sprite", "character", "animated", "firefly"):
            fps = self._def.get("fps", self._def.get("anim_fps", 8))
            self._frame_elapsed += dt
            if self._frame_elapsed >= 1.0 / max(fps, 1):
                self._frame_elapsed = 0.0
                if t == "animated":
                    import sprites as sp
                    key = self._def.get("sprite_key", "")
                    frames = getattr(sp, f"{key}_FRAMES", 1)
                    self._frame_index = (self._frame_index + 1) % frames
                elif t == "firefly":
                    import sprites as sp
                    key = self._def.get("sprite_key", "")
                    frames = getattr(sp, f"{key}_FRAMES", 1)
                    self._frame_index = (self._frame_index + 1) % frames
                else:
                    idle_frames = self._def.get("idle_frames", [0])
                    self._frame_index = (self._frame_index + 1) % len(idle_frames)

            if t == "character":
                self._update_walk(dt)

    def _update_walk(self, dt: float):
        waypoints = self._def.get("waypoints", [])
        if len(waypoints) < 2 or self._walk_pos is None:
            return
        speed = self._def.get("walk_speed", 0.5)
        target = waypoints[self._waypoint_index]
        dx = target[0] - self._walk_pos[0]
        dy = target[1] - self._walk_pos[1]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            self._waypoint_index = (self._waypoint_index + 1) % len(waypoints)
        else:
            move = speed * dt * config.TARGET_FPS
            self._walk_pos[0] += (dx / dist) * move
            self._walk_pos[1] += (dy / dist) * move

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface):
        if self.surface is None:
            return

        t = self.layer_type

        if t == "scroll":
            w = self.surface.get_width()
            x = int(-(self._scroll_offset % w))
            while x < config.RENDER_WIDTH:
                surface.blit(self.surface, (x, int(self._def.get("y", 0))))
                x += w

        elif t == "character" and self._walk_pos is not None:
            frame_size = self._def.get("frame_size", [16, 24])
            idle_frames = self._def.get("idle_frames", [0])
            frame_idx = idle_frames[self._frame_index % len(idle_frames)]
            src = pygame.Rect(frame_idx * frame_size[0], 0, frame_size[0], frame_size[1])
            surface.blit(self.surface, (int(self._walk_pos[0]), int(self._walk_pos[1])), src)

        elif t == "animated":
            import sprites as sp
            key = self._def.get("sprite_key", "")
            w = getattr(sp, f"{key}_W")
            h = getattr(sp, f"{key}_H")
            src = pygame.Rect(self._frame_index * w, 0, w, h)
            x = int(self._def.get("x", 0))
            y = int(self._def.get("y", 0))
            surface.blit(self.surface, (x, y), src)

        elif t == "firefly":
            import sprites as sp
            key = self._def.get("sprite_key", "")
            w = getattr(sp, f"{key}_W")
            h = getattr(sp, f"{key}_H")
            src = pygame.Rect(self._frame_index * w, 0, w, h)
            drift = self._def.get("drift", {})
            base_x = float(self._def.get("x", 0))
            base_y = float(self._def.get("y", 0))
            period = drift.get("period", 5.0)
            phase = drift.get("phase", 0.0)
            amp_x = drift.get("x", 0)
            amp_y = drift.get("y", 0)
            t_val = self._elapsed
            x_off = amp_x * math.sin(t_val * (2 * math.pi / period) + phase)
            y_off = amp_y * math.sin(t_val * (2 * math.pi / period * 0.7) + phase)
            draw_x = int(base_x + x_off)
            draw_y = int(base_y + y_off)
            surface.blit(self.surface, (draw_x, draw_y), src)

        elif t == "static":
            import sprites as sp
            key = self._def.get("sprite_key", "")
            x = int(self._def.get("x", 0))
            y = int(self._def.get("y", 0))
            if self._def.get("sway"):
                y += round(math.sin(self._elapsed * (2 * math.pi / 4.0)))
            surface.blit(self.surface, (x, y))

        else:
            # Legacy fallback
            frame_size = self._def.get("frame_size")
            if frame_size:
                idle_frames = self._def.get("idle_frames", [0])
                frame_idx = idle_frames[self._frame_index % len(idle_frames)]
                src = pygame.Rect(frame_idx * frame_size[0], 0, frame_size[0], frame_size[1])
                surface.blit(self.surface, (int(self._def.get("x", 0)), int(self._def.get("y", 0))), src)
            else:
                surface.blit(self.surface, (int(self._def.get("x", 0)), int(self._def.get("y", 0))))


# ---------------------------------------------------------------------------

class Scene:
    def __init__(self, scene_dir: str):
        self.scene_dir = scene_dir
        self.name = os.path.basename(scene_dir)
        self.background_color = (34, 85, 34)
        self.background: Optional[pygame.Surface] = None
        self.layers: List[Layer] = []
        self.events: Dict[str, Any] = {}
        self.ambient_paused = False
        self._paused_layer_ids: List[str] = []
        self._elapsed = 0.0
        self._load()

    def _load(self):
        scene_path = os.path.join(self.scene_dir, "scene.json")
        events_path = os.path.join(self.scene_dir, "events.json")

        if os.path.exists(scene_path):
            with open(scene_path) as f:
                scene_def = json.load(f)

            bg_color = scene_def.get("background_color")
            if bg_color:
                self.background_color = tuple(bg_color)

            bg_path = scene_def.get("background")
            if bg_path and os.path.exists(bg_path):
                try:
                    raw = pygame.image.load(bg_path).convert()
                    self.background = pygame.transform.scale(raw, (config.RENDER_WIDTH, config.RENDER_HEIGHT))
                except Exception as e:
                    logger.warning("Could not load background %s: %s", bg_path, e)

            for layer_def in scene_def.get("layers", []):
                self.layers.append(Layer(layer_def))
        else:
            logger.warning("No scene.json found at %s", scene_path)

        if os.path.exists(events_path):
            with open(events_path) as f:
                self.events = json.load(f)
        else:
            logger.warning("No events.json found at %s", events_path)

    def get_event_sequence(self, event_name: str):
        event = self.events.get(event_name)
        if event is None:
            logger.warning("Unknown event: %s", event_name)
            return None
        return event.get("sequence", [])

    def update(self, dt: float):
        self._elapsed += dt
        for layer in self.layers:
            layer_paused = self.ambient_paused and (
                not self._paused_layer_ids or layer.id in self._paused_layer_ids
            )
            layer.update(dt, layer_paused, self._elapsed)

    def draw(self, surface: pygame.Surface):
        if self.background:
            surface.blit(self.background, (0, 0))
        else:
            surface.fill(self.background_color)
        for layer in self.layers:
            layer.draw(surface)

    def pause_layers(self, layer_ids: List[str]):
        self.ambient_paused = True
        self._paused_layer_ids = layer_ids

    def resume_layers(self, layer_ids: List[str]):
        self.ambient_paused = False
        self._paused_layer_ids = []
