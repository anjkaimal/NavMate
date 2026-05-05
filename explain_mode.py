from typing import Callable

from pynput import mouse
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

import config
from logger import get_logger

log = get_logger(__name__)

# Signature: (x, y, width, height, cursor_x, cursor_y) -> None
ExplainCallback = Callable[[int, int, int, int, int, int], None]


class ExplainMode:
    def __init__(self, ai_callback: ExplainCallback) -> None:
        self._ai_callback = ai_callback
        self._active = False
        self._mx = 0
        self._my = 0
        self._tooltip: QLabel | None = None
        self._dismiss_timer = QTimer()
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._hide_tooltip)
        self._listener: mouse.Listener | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_mouse_tracking(self) -> None:
        self._listener = mouse.Listener(on_move=self._on_mouse_move)
        self._listener.daemon = True
        self._listener.start()
        log.debug("Mouse tracking started")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self._hide_tooltip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def toggle(self) -> bool:
        self._active = not self._active
        log.debug(f"Explain mode {'ON' if self._active else 'OFF'}")
        if not self._active:
            self._hide_tooltip()
        return self._active

    @property
    def is_active(self) -> bool:
        return self._active

    def explain_at_cursor(self) -> None:
        if not self._active:
            return
        r = config.EXPLAIN_REGION_RADIUS
        x = max(0, self._mx - r)
        y = max(0, self._my - r)
        log.debug(f"Explain at cursor ({self._mx},{self._my}), region ({x},{y},{r*2},{r*2})")
        self._ai_callback(x, y, r * 2, r * 2, self._mx, self._my)

    def show_tooltip(self, text: str, mx: int, my: int) -> None:
        self._hide_tooltip()

        self._tooltip = QLabel(text)
        self._tooltip.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._tooltip.setWordWrap(True)
        self._tooltip.setMaximumWidth(320)
        self._tooltip.setStyleSheet("""
            QLabel {
                background-color: rgba(18, 18, 24, 235);
                color: #FFFFFF;
                border: 1px solid #00FF99;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                line-height: 1.4;
            }
        """)
        self._tooltip.adjustSize()

        screen = QApplication.primaryScreen().geometry()
        tx = min(mx + 18, screen.width() - self._tooltip.width() - 8)
        ty = min(my + 18, screen.height() - self._tooltip.height() - 8)
        self._tooltip.move(tx, ty)
        self._tooltip.show()
        self._tooltip.raise_()

        self._dismiss_timer.start(config.EXPLAIN_TOOLTIP_DURATION)
        log.debug(f"Tooltip shown at ({tx},{ty})")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_mouse_move(self, x: int, y: int) -> None:
        self._mx = x
        self._my = y

    def _hide_tooltip(self) -> None:
        self._dismiss_timer.stop()
        if self._tooltip:
            self._tooltip.hide()
            self._tooltip.deleteLater()
            self._tooltip = None
