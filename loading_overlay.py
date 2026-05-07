import math

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from logger import get_logger

log = get_logger(__name__)

_MESSAGES = [
    "Capturing your screen…",
    "Analysing the interface…",
    "Working out the answer…",
]

# ── Colour palette ───────────────────────────────────────────────────────────
_BG          = QColor(8,  10, 22, 252)
_BORDER      = QColor(0, 207, 255,  80)
_HEAD_DARK   = QColor(10, 28,  90)
_HEAD_MID    = QColor(16, 42, 130)
_HEAD_LIGHT  = QColor(22, 58, 165)
_EYE_COLOR   = QColor(0,  207, 255)     # electric cyan
_PUPIL       = QColor(5,  10,  38)
_SHINE       = QColor(255, 255, 255, 220)
_DOT_ON      = QColor(0,  207, 255, 255)
_DOT_OFF     = QColor(0,  207, 255,  55)
_TEXT_COLOR  = QColor(180, 220, 255)
_CANCEL_TEXT = QColor(80, 120, 170)


class LoadingOverlay(QWidget):
    """Animated mascot shown while the AI processes a query."""

    W, H = 250, 225

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
                color: rgba(70, 110, 170, 170);
                border: none;
                font-size: 11px;
                text-decoration: underline;
            }
            QPushButton:hover { color: rgba(0, 207, 255, 200); }
        """)
        self._cancel_btn.setGeometry(self.W // 2 - 24, self.H - 24, 48, 18)
        self._cancel_btn.clicked.connect(self.hide_loading)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_loading(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - self.W // 2,
            screen.height() - self.H - 60,
        )
        self._frame   = 0
        self._msg_idx = 0
        self.show()
        self.raise_()
        self._anim_timer.start(50)      # 20 fps — smooth
        self._msg_timer.start(2000)     # cycle messages every 2 s
        log.debug("Loading overlay shown")

    def hide_loading(self) -> None:
        self._anim_timer.stop()
        self._msg_timer.stop()
        self.hide()
        log.debug("Loading overlay hidden")

    def advance_message(self) -> None:
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

        # ── Background card ───────────────────────────────────────────
        p.setPen(QPen(_BORDER, 1))
        p.setBrush(_BG)
        p.drawRoundedRect(1, 1, W - 2, H - 2, 22, 22)

        # ── Face geometry ─────────────────────────────────────────────
        cx, cy, cr = W // 2, 72, 36

        # Pulsing glow behind head
        pulse = (math.sin(self._frame * 0.09) + 1) / 2
        gr    = int(cr + 10 + pulse * 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 207, 255, int(14 + pulse * 22)))
        p.drawEllipse(cx - gr, cy - gr, gr * 2, gr * 2)

        # Head — layered circles for depth
        p.setBrush(_HEAD_DARK)
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)
        p.setBrush(_HEAD_MID)
        p.drawEllipse(cx - cr + 2, cy - cr + 2, (cr - 2) * 2, (cr - 2) * 2)
        p.setBrush(_HEAD_LIGHT)
        p.drawEllipse(cx - cr + 5, cy - cr + 5, (cr - 5) * 2, (cr - 5) * 2)

        # ── Eyes ──────────────────────────────────────────────────────
        blink = (self._frame % 80) < 5

        if blink:
            p.setPen(QPen(_EYE_COLOR, 2.5,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(cx - 13, cy - 1, cx - 4, cy - 1)
            p.drawLine(cx + 4,  cy - 1, cx + 13, cy - 1)
        else:
            drift = int(math.sin(self._frame * 0.03) * 2)

            # Whites
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_EYE_COLOR)
            p.drawEllipse(cx - 14, cy - 9, 11, 14)
            p.drawEllipse(cx + 3,  cy - 9, 11, 14)

            # Pupils
            p.setBrush(_PUPIL)
            p.drawEllipse(cx - 12 + drift, cy - 7, 7, 10)
            p.drawEllipse(cx + 5  + drift, cy - 7, 7, 10)

            # Shine dots
            p.setBrush(_SHINE)
            p.drawEllipse(cx - 13 + drift, cy - 9, 3, 3)
            p.drawEllipse(cx + 4  + drift, cy - 9, 3, 3)

        # ── Smile ─────────────────────────────────────────────────────
        p.setPen(QPen(_EYE_COLOR, 2.2,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRect(cx - 10, cy + 8, 20, 12), 200 * 16, 140 * 16)

        # ── Thinking dots ─────────────────────────────────────────────
        dot_y    = cy + cr + 18
        dot_step = (self._frame // 10) % 3

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            active = (dot_step == i)
            r = 6 if active else 4
            p.setBrush(_DOT_ON if active else _DOT_OFF)
            dx = W // 2 - 20 + i * 20
            p.drawEllipse(dx - r, dot_y - r, r * 2, r * 2)

        # ── Status text ───────────────────────────────────────────────
        p.setPen(_TEXT_COLOR)
        p.setFont(QFont("Segoe UI", 13))
        p.drawText(
            QRect(10, dot_y + 16, W - 20, 28),
            Qt.AlignmentFlag.AlignCenter,
            _MESSAGES[self._msg_idx],
        )

        p.end()
