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
# Accessible palette: dark-blue boxes, white text on opaque badge backgrounds.
# All colour pairs meet WCAG AA contrast (≥ 4.5:1 on their respective backgrounds).
OVERLAY_BG_ALPHA = 110                  # 0–255 dim over the screen

OVERLAY_BOX_COLOR        = "#1E6FEB"   # border + corner dots
OVERLAY_BOX_FILL         = (10, 30, 100, 55)   # rgba inner highlight
OVERLAY_BOX_WIDTH        = 3

OVERLAY_LABEL_BG         = "#1A4FD6"   # solid blue pill behind label text
OVERLAY_LABEL_COLOR      = "#FFFFFF"
OVERLAY_LABEL_FONT_SIZE  = 15          # +25 % over original 12 pt

OVERLAY_EXPL_BG          = (15, 15, 40, 218)   # near-opaque dark navy pill
OVERLAY_EXPL_BORDER      = "#1E6FEB"
OVERLAY_EXPL_COLOR       = "#FFFFFF"
OVERLAY_EXPL_FONT_SIZE   = 14          # +27 % over original 11 pt

OVERLAY_CORNER_COLOR     = "#5AABFF"   # lighter blue accent dots
OVERLAY_BADGE_RADIUS     = 5           # px, rounded corners on badges

# --- Explain Mode ---
EXPLAIN_REGION_RADIUS = 150     # pixels around cursor for crop
EXPLAIN_TOOLTIP_DURATION = 6000 # ms before auto-dismiss

# --- Logging ---
LOG_FILE = "navmate_debug.log"
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOG_BACKUP_COUNT = 3
