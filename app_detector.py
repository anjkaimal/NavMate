import win32gui
from logger import get_logger

log = get_logger(__name__)

# Map app key → list of substrings matched against the active window title (lowercase)
_APP_PATTERNS: dict[str, list[str]] = {
    "zoom":   ["zoom"],
    "chrome": ["google chrome", "chromium", "chrome"],
    "vscode": ["visual studio code", "vs code"],
}


def get_active_app() -> str:
    """Return an app key for the current foreground window, or 'generic'."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd).lower()
        log.debug(f"Active window: '{title}'")
        for app_key, patterns in _APP_PATTERNS.items():
            if any(p in title for p in patterns):
                log.debug(f"Matched app: {app_key}")
                return app_key
    except Exception as e:
        log.warning(f"App detection failed: {e}")
    return "generic"
