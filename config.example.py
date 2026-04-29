# Display
RENDER_WIDTH = 240
RENDER_HEIGHT = 160
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320
SCALE = 2
TARGET_FPS = 12

# Display driver
#   "fb"  — direct framebuffer via mmap (Raspberry Pi / Bookworm, no SDL display required)
#   "sdl" — pygame window (desktop development)
DISPLAY_DRIVER = "fb"
FRAMEBUFFER = "/dev/fb0"

# Server
HTTP_PORT = 5000
HTTP_HOST = "0.0.0.0"

# Scene
DEFAULT_SCENE = "forest"

# Logging
LOG_LEVEL = "INFO"
