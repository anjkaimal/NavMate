import threading

import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

from logger import get_logger

log = get_logger(__name__)


class _HotkeyBridge(QObject):
    """Lives on the main thread; signals are emitted from the hotkey thread.
    Qt automatically queues cross-thread signal delivery to the main event loop."""
    guide_triggered = pyqtSignal()
    explain_toggle_triggered = pyqtSignal()


class HotkeyListener:
    def __init__(self) -> None:
        self.bridge = _HotkeyBridge()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._register, daemon=True, name="hotkey")
        self._thread.start()
        log.debug("Hotkey listener thread started")

    def _register(self) -> None:
        try:
            keyboard.add_hotkey("ctrl+shift+h", self._fire_guide)
            log.debug("Registered: ctrl+shift+h (guide)")
        except Exception as exc:
            log.error(f"Failed to register guide hotkey: {exc}")

        try:
            keyboard.add_hotkey("ctrl+shift+e", self._fire_explain_toggle)
            log.debug("Registered: ctrl+shift+e (explain toggle)")
        except Exception as exc:
            log.error(f"Failed to register explain hotkey: {exc}")

        keyboard.wait()  # blocks this daemon thread indefinitely

    def _fire_guide(self) -> None:
        log.debug("Hotkey fired: guide")
        self.bridge.guide_triggered.emit()

    def _fire_explain_toggle(self) -> None:
        log.debug("Hotkey fired: explain toggle")
        self.bridge.explain_toggle_triggered.emit()

    def stop(self) -> None:
        keyboard.unhook_all()
        log.debug("Hotkeys unregistered")
