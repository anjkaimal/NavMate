import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

import cache
from ai_client import AIResponseError, query_ai
from app_detector import get_active_app
from config import ANTHROPIC_API_KEY
from explain_mode import ExplainMode
from hotkey import HotkeyListener
from input_dialog import QueryDialog
from logger import get_logger
from overlay import OverlayWindow
from screenshot import capture_region, capture_screen

log = get_logger("main")


class _Bridge(QObject):
    """Signals used to hand results from worker threads back to the Qt main thread."""
    elements_ready = pyqtSignal(list)
    explain_ready = pyqtSignal(str, int, int)  # text, cursor_x, cursor_y
    error_occurred = pyqtSignal(str, str)       # title, message


class NavMate:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self._bridge = _Bridge()
        self._last_query = ""

        self.dialog = QueryDialog()
        self.overlay = OverlayWindow()
        self.hotkeys = HotkeyListener()
        self.explain = ExplainMode(ai_callback=self._explain_region_async)

        self._wire_signals()

    def _wire_signals(self) -> None:
        # hotkey → UI actions (already on Qt thread via queued connection)
        self.hotkeys.bridge.guide_triggered.connect(self._on_guide_hotkey)
        self.hotkeys.bridge.explain_toggle_triggered.connect(self._on_explain_toggle)

        # dialog → pipeline
        self.dialog.query_submitted.connect(self._on_query_submitted)

        # overlay bonus actions
        self.overlay.try_again_requested.connect(self._on_try_again)

        # bridge → UI (ensures worker-thread results reach the main thread)
        self._bridge.elements_ready.connect(self.overlay.show_elements)
        self._bridge.explain_ready.connect(self._on_explain_ready)
        self._bridge.error_occurred.connect(self._show_error)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not ANTHROPIC_API_KEY:
            QMessageBox.critical(
                None,
                "NavMate — Missing API Key",
                "The ANTHROPIC_API_KEY environment variable is not set.\n\n"
                "Set it in your shell before launching NavMate:\n"
                "    set ANTHROPIC_API_KEY=sk-ant-...",
            )
            sys.exit(1)

        self.hotkeys.start()
        self.explain.start_mouse_tracking()
        log.debug("NavMate started — Ctrl+Shift+H to guide, Ctrl+Shift+E for explain mode")

    # ------------------------------------------------------------------
    # Hotkey handlers (main thread)
    # ------------------------------------------------------------------

    def _on_guide_hotkey(self) -> None:
        if self.explain.is_active:
            self.explain.explain_at_cursor()
        else:
            self.overlay.clear()
            self.dialog.show_centered()

    def _on_explain_toggle(self) -> None:
        active = self.explain.toggle()
        log.debug(f"Explain mode: {'ON' if active else 'OFF'}")

    # ------------------------------------------------------------------
    # Query pipeline
    # ------------------------------------------------------------------

    def _on_query_submitted(self, query: str) -> None:
        self._last_query = query
        log.debug(f"Query: '{query}'")
        app_key = get_active_app()

        try:
            _img, b64 = capture_screen()
        except Exception as exc:
            log.error(f"Screenshot failed: {exc}")
            self._bridge.error_occurred.emit("Screenshot Failed", str(exc))
            return

        self._run_guide_async(b64, query, app_key)

    def _run_guide_async(self, b64: str, query: str, app_key: str) -> None:
        def worker() -> None:
            try:
                elements = query_ai(b64, query, app_key, mode="guide")
                cache.save(b64, elements, query)
                self._bridge.elements_ready.emit(elements)
            except AIResponseError as exc:
                log.error(f"AI error: {exc}")
                self._bridge.error_occurred.emit("AI Response Error", str(exc))
            except Exception as exc:
                log.error(f"Unexpected error: {exc}", exc_info=True)
                self._bridge.error_occurred.emit("Unexpected Error", str(exc))

        threading.Thread(target=worker, daemon=True, name="ai-guide").start()

    def _on_try_again(self) -> None:
        b64, _result, query = cache.load()
        if not b64 or not query:
            log.warning("Try Again pressed but cache is empty")
            return
        log.debug("Try Again: reusing cached screenshot")
        app_key = get_active_app()
        self._run_guide_async(b64, query, app_key)

    # ------------------------------------------------------------------
    # Explain Mode pipeline
    # ------------------------------------------------------------------

    def _explain_region_async(
        self, x: int, y: int, w: int, h: int, mx: int, my: int
    ) -> None:
        def worker() -> None:
            try:
                _img, b64 = capture_region(x, y, w, h)
                app_key = get_active_app()
                result = query_ai(b64, "What does this UI element do?", app_key, mode="explain")
                text = result.get("explanation", "No explanation available.")
                self._bridge.explain_ready.emit(text, mx, my)
            except Exception as exc:
                log.error(f"Explain region error: {exc}", exc_info=True)
                self._bridge.error_occurred.emit("Explain Error", str(exc))

        threading.Thread(target=worker, daemon=True, name="ai-explain").start()

    def _on_explain_ready(self, text: str, mx: int, my: int) -> None:
        self.explain.show_tooltip(text, mx, my)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(None, f"NavMate — {title}", message)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running when all dialogs close

    navmate = NavMate(app)
    navmate.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
