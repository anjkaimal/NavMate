import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

import cache
from ai_client import AIResponseError
from app_detector import get_active_app
from assistant_dock import AssistantDock
from config import ANTHROPIC_API_KEY
from explain_mode import ExplainMode
from grid_analyzer import analyze_grid
from input_dialog import QueryDialog
from loading_overlay import LoadingOverlay
from logger import get_logger
from overlay import OverlayWindow
from screenshot import capture_region
from voice import speak

log = get_logger("main")


class _Bridge(QObject):
    """Thread-safe signals from worker threads → Qt main thread."""
    elements_ready  = pyqtSignal(list, int, int)  # elements, full_phys_w, full_phys_h
    status_update   = pyqtSignal(int)             # loading message index (0/1/2)
    explain_ready   = pyqtSignal(str, int, int)   # text, cursor_x, cursor_y
    error_occurred  = pyqtSignal(str, str)        # title, message


class NavMate:
    def __init__(self, app: QApplication) -> None:
        self.app    = app
        self._bridge = _Bridge()

        self.dialog  = QueryDialog()
        self.overlay = OverlayWindow()
        self.loading = LoadingOverlay()
        self.dock    = AssistantDock()
        self.explain = ExplainMode(ai_callback=self._explain_region_async)

        self._wire_signals()

    def _wire_signals(self) -> None:
        self.dock.ask_requested.connect(self._on_ask_question)
        self.dock.explain_toggled.connect(self._on_explain_toggle)

        self.dialog.query_submitted.connect(self._on_query_submitted)
        self.overlay.try_again_requested.connect(self._on_try_again)

        # Route all bridge results through handlers so the loading overlay is
        # always hidden before the next UI action regardless of success/failure.
        self._bridge.elements_ready.connect(self._on_elements_ready)
        self._bridge.status_update.connect(self.loading.advance_message)
        self._bridge.explain_ready.connect(self._on_explain_ready)
        self._bridge.error_occurred.connect(self._on_error)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not ANTHROPIC_API_KEY:
            QMessageBox.critical(
                None,
                "NavMate — Missing API Key",
                "The ANTHROPIC_API_KEY environment variable is not set.\n\n"
                "Set it before running NavMate:\n"
                "    set ANTHROPIC_API_KEY=sk-ant-...",
            )
            sys.exit(1)

        self.explain.start_mouse_tracking()
        self.dock.show()
        log.debug("NavMate ready — dock visible")

    # ------------------------------------------------------------------
    # Dock handlers  (Qt main thread)
    # ------------------------------------------------------------------

    def _on_ask_question(self) -> None:
        self.overlay.clear()
        self.dialog.show_centered()

    def _on_explain_toggle(self) -> None:
        active = self.explain.toggle()
        self.dock.set_explain_active(active)
        log.debug(f"Explain mode: {'ON' if active else 'OFF'}")

    # ------------------------------------------------------------------
    # Guide pipeline
    # ------------------------------------------------------------------

    def _on_query_submitted(self, query: str) -> None:
        log.debug(f"Query: '{query}'")
        app_key = get_active_app()
        self.loading.show_loading()          # show mascot immediately
        self._run_guide_async(query, app_key)

    def _run_guide_async(self, query: str, app_key: str) -> None:
        def worker() -> None:
            def status_cb(idx: int) -> None:
                self._bridge.status_update.emit(idx)

            try:
                elements, full_w, full_h = analyze_grid(
                    query, app_key, status_cb=status_cb
                )
                cache.save("", elements, query, full_w, full_h)
                self._bridge.elements_ready.emit(elements, full_w, full_h)
            except AIResponseError as exc:
                log.error(f"AI error: {exc}")
                self._bridge.error_occurred.emit("AI Response Error", str(exc))
            except Exception as exc:
                log.error(f"Unexpected error: {exc}", exc_info=True)
                self._bridge.error_occurred.emit("Unexpected Error", str(exc))

        threading.Thread(target=worker, daemon=True, name="ai-guide").start()

    def _on_try_again(self) -> None:
        _, _, query, _, _ = cache.load()
        if not query:
            log.warning("Try Again pressed but cache is empty")
            return
        log.debug("Try Again: re-running grid analysis with same query")
        app_key = get_active_app()
        self.overlay.clear()
        self.loading.show_loading()
        self._run_guide_async(query, app_key)

    # ------------------------------------------------------------------
    # Bridge result handlers  (Qt main thread)
    # ------------------------------------------------------------------

    def _on_elements_ready(self, elements: list, full_w: int, full_h: int) -> None:
        self.loading.hide_loading()
        self.overlay.show_elements(elements, full_w, full_h)
        if elements:
            text = (elements[0].get("voice_instruction")
                    or elements[0].get("instruction")
                    or elements[0].get("explanation", ""))
            speak(text)

    def _on_error(self, title: str, message: str) -> None:
        self.loading.hide_loading()
        QMessageBox.warning(None, f"NavMate — {title}", message)

    # ------------------------------------------------------------------
    # Explain Mode pipeline
    # ------------------------------------------------------------------

    def _explain_region_async(
        self, x: int, y: int, w: int, h: int, mx: int, my: int
    ) -> None:
        from ai_client import query_ai

        def worker() -> None:
            try:
                _img, b64 = capture_region(x, y, w, h)
                app_key = get_active_app()
                result = query_ai(b64, "What does this UI element do?", app_key, mode="explain")
                text = result.get("explanation", "No explanation available.")
                self._bridge.explain_ready.emit(text, mx, my)
            except Exception as exc:
                log.error(f"Explain error: {exc}", exc_info=True)
                self._bridge.error_occurred.emit("Explain Error", str(exc))

        threading.Thread(target=worker, daemon=True, name="ai-explain").start()

    def _on_explain_ready(self, text: str, mx: int, my: int) -> None:
        self.explain.show_tooltip(text, mx, my)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    navmate = NavMate(app)
    navmate.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
