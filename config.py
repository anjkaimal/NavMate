import os

# --- AI ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = "claude-sonnet-4-6"
AI_MAX_TOKENS = 1024

# --- Screenshot ---
SCREENSHOT_MAX_DIMENSION = 1920

# --- Design tokens ---
# Electric cyan accent used across all UI components.
ACCENT          = "#00CFFF"
ACCENT_DARK     = "#0099CC"
ACCENT_DIM_RGBA = (0, 207, 255, 45)   # subtle border tint

# --- Overlay ---
OVERLAY_BG_ALPHA = 115                 # 0–255 screen dim

# Target-element box
OVERLAY_BOX_COLOR        = "#00CFFF"           # corner brackets + border
OVERLAY_BOX_FILL         = (0, 175, 215, 18)   # rgba subtle fill
OVERLAY_BOX_WIDTH        = 2

# Label badge above the box
OVERLAY_LABEL_BG         = "#050A1C"           # deep dark card
OVERLAY_LABEL_BORDER     = "#00CFFF"           # cyan pill border
OVERLAY_LABEL_COLOR      = "#FFFFFF"
OVERLAY_LABEL_FONT_SIZE  = 16

# Instruction bar at bottom of screen
OVERLAY_EXPL_BG          = (6, 9, 22, 238)     # near-opaque dark
OVERLAY_EXPL_BORDER      = "#00CFFF"
OVERLAY_EXPL_COLOR       = "#FFFFFF"
OVERLAY_EXPL_FONT_SIZE   = 14                  # kept for backwards compat
OVERLAY_INSTR_FONT_SIZE  = 20                  # large for easy reading

OVERLAY_CORNER_COLOR     = "#00CFFF"
OVERLAY_BADGE_RADIUS     = 8

# Try Again / Esc buttons
OVERLAY_BTN_BG           = "rgba(0, 150, 200, 18)"
OVERLAY_BTN_BORDER       = "rgba(0, 207, 255, 100)"
OVERLAY_BTN_COLOR        = "#00CFFF"

# --- Explain Mode ---
EXPLAIN_REGION_RADIUS    = 150     # pixels around cursor for crop
EXPLAIN_TOOLTIP_DURATION = 6000    # ms before auto-dismiss

# --- Logging ---
LOG_FILE         = "navmate_debug.log"
LOG_MAX_BYTES    = 2 * 1024 * 1024  # 2 MB
LOG_BACKUP_COUNT = 3
