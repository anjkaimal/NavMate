import os

# --- Hotkeys ---
HOTKEY_GUIDE = "ctrl+shift+h"
HOTKEY_EXPLAIN_TOGGLE = "ctrl+shift+e"

# --- AI ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = "claude-sonnet-4-6"
AI_MAX_TOKENS = 1024

# --- Screenshot ---
SCREENSHOT_MAX_DIMENSION = 1920

# --- Overlay ---
OVERLAY_BG_ALPHA = 100          # 0–255, applied to black background
OVERLAY_BOX_COLOR = "#00FF99"
OVERLAY_BOX_WIDTH = 3
OVERLAY_LABEL_COLOR = "#FFFFFF"
OVERLAY_EXPLANATION_COLOR = "#FFE566"
OVERLAY_FONT_SIZE = 12

# --- Explain Mode ---
EXPLAIN_REGION_RADIUS = 150     # pixels around cursor for crop
EXPLAIN_TOOLTIP_DURATION = 6000 # ms before auto-dismiss

# --- Logging ---
LOG_FILE = "navmate_debug.log"
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOG_BACKUP_COUNT = 3
