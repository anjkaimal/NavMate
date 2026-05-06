import math

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from logger import get_logger

log = get_logger(__name__)

_MESSAGES = [
    "Capturing screen…",
    "Analyzing UI elements…",
    "Generating response…",
]

# Colours
_BG          = QColor(12, 18, 42, 248)
_BORDER      = QColor(30, 111, 235, 100)
_HEAD_DARK   = QColor(18, 52, 130)
_HEAD_LIGHT  = QColor(26, 70, 165)
_EYE_COLOR   = QColor(110, 195, 255)
_PUPIL       = QColor(8, 16, 52)
_SHINE       = QColor(255, 255, 255, 210)
_DOT_ON      = QColor(90, 171, 255, 255)
_DOT_OFF     = QColor(90, 171, 255, 70)
_TEXT_COLOR  = QColor(175, 205, 255)
_CANCEL_TEXT = QColor(100, 130, 180)


class LoadingOverlay(QWidget):
    """Animated mascot shown while the AI is processing a query."""

    W, H = 220, 195

    def __init__(self) -> None:
        super().__init__()
        self._frame   = 0
        self._msg_idx = 0

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)

        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(False)
        self._msg_timer.timeout.connect(self._next_message)

        self._build_ui()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        self._cancel_btn = QPushButton("cancel", self)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(90, 130, 190, 180);
                border: none;
                font-size: 10px;
                text-decoration: underline;
            }
            QPushButton:hover { color: rgba(150, 180, 255, 220); }
        """)
        self._cancel_btn.setGeometry(self.W // 2 - 22, self.H - 22, 44, 16)
        self._cancel_btn.clicked.connect(self.hide_loading)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_loading(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - self.W // 2,
            screen.height() - self.H - 55,
        )
        self._frame   = 0
        self._msg_idx = 0
        self.show()
        self.raise_()
        self._anim_timer.start(80)     # ~12 fps — smooth blink/glow
        self._msg_timer.start(1800)    # cycle messages every 1.8 s
        log.debug("Loading overlay shown")

    def hide_loading(self) -> None:
        self._anim_timer.stop()
        self._msg_timer.stop()
        self.hide()
        log.debug("Loading overlay hidden")

    def advance_message(self) -> None:
        """Manually step to the next status message (call from worker thread via signal)."""
        self._msg_idx = min(self._msg_idx + 1, len(_MESSAGES) - 1)
        self.update()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._frame += 1
        self.update()

    def _next_message(self) -> None:
        self._msg_idx = (self._msg_idx + 1) % len(_MESSAGES)
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W, H = self.W, self.H

        # ── Background pill ──────────────────────────────────────────
        p.setPen(QPen(_BORDER, 1))
        p.setBrush(_BG)
        p.drawRoundedRect(1, 1, W - 2, H - 2, 20, 20)

        # ── Face geometry ────────────────────────────────────────────
        cx, cy, cr = W // 2, 60, 30

        # Pulsing glow behind head
        pulse = (math.sin(self._frame * 0.08) + 1) / 2          # 0–1
        gr    = int(cr + 8 + pulse * 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 111, 235, int(18 + pulse * 24)))
        p.drawEllipse(cx - gr, cy - gr, gr * 2, gr * 2)

        # Head body
        p.setBrush(_HEAD_DARK)
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)
        p.setBrush(_HEAD_LIGHT)
        p.drawEllipse(cx - cr + 3, cy - cr + 3, (cr - 3) * 2, (cr - 3) * 2)

        # ── Eyes ─────────────────────────────────────────────────────
        # Blink for 4 frames (~320 ms) every 75 frames (~6 s)
        blink = (self._frame % 75) < 4

        if blink:
            p.setPen(QPen(_EYE_COLOR, 2.5,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(cx - 12, cy - 1, cx - 4, cy - 1)
            p.drawLine(cx + 4,  cy - 1, cx + 12, cy - 1)
        else:
            drift = int(math.sin(self._frame * 0.025) * 1.5)

            # Whites
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_EYE_COLOR)
            p.drawEllipse(cx - 13, cy - 8, 10, 13)
            p.drawEllipse(cx + 3,  cy - 8, 10, 13)

            # Pupils
            p.setBrush(_PUPIL)
            p.drawEllipse(cx - 11 + drift, cy - 6, 6, 9)
            p.drawEllipse(cx + 5  + drift, cy - 6, 6, 9)

            # Shine
            p.setBrush(_SHINE)
            p.drawEllipse(cx - 12 + drift, cy - 8, 3, 3)
            p.drawEllipse(cx + 4  + drift, cy - 8, 3, 3)

        # ── Mouth (arc smile) ────────────────────────────────────────
        p.setPen(QPen(_EYE_COLOR, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRect(cx - 9, cy + 6, 18, 11), 200 * 16, 140 * 16)

        # ── Thinking dots (one lights up at a time, cycles left→right) ──
        dot_y    = cy + cr + 14
        dot_step = (self._frame // 8) % 3    # 0, 1, 2

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            active = (dot_step == i)
            r = 5 if active else 4
            p.setBrush(_DOT_ON if active else _DOT_OFF)
            dx = W // 2 - 18 + i * 18
            p.drawEllipse(dx - r, dot_y - r, r * 2, r * 2)

        # ── Status text ───────────────────────────────────────────────
        p.setPen(_TEXT_COLOR)
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRect(8, dot_y + 14, W - 16, 24),
                   Qt.AlignmentFlag.AlignCenter,
                   _MESSAGES[self._msg_idx])

        p.end()
