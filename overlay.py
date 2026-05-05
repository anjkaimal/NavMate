from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

import config
from logger import get_logger

log = get_logger(__name__)


class OverlayWindow(QWidget):
    try_again_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._elements: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._try_again_btn = QPushButton("↺  Try Again", self)
        self._try_again_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 180, 100, 210);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover  { background-color: rgba(0, 220, 130, 230); }
            QPushButton:pressed { background-color: rgba(0, 140, 80, 230); }
        """)
        self._try_again_btn.clicked.connect(self.try_again_requested)
        self._try_again_btn.hide()

        self._esc_hint = QPushButton("Press Esc to close", self)
        self._esc_hint.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: rgba(160, 160, 160, 140);
                border: none;
                font-size: 11px;
            }
        """)
        self._esc_hint.setEnabled(False)
        self._esc_hint.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_elements(self, elements: list[dict]) -> None:
        self._elements = elements
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        m = 16
        bw, bh = 128, 36
        self._try_again_btn.setGeometry(screen.width() - bw - m, screen.height() - bh - m, bw, bh)
        self._try_again_btn.show()
        self._try_again_btn.raise_()

        hw = 160
        self._esc_hint.setGeometry(screen.width() // 2 - hw // 2, screen.height() - 26, hw, 20)
        self._esc_hint.show()
        self._esc_hint.raise_()

        self.showFullScreen()
        self.raise_()
        self.update()
        log.debug(f"Overlay showing {len(elements)} elements")

    def clear(self) -> None:
        self._elements = []
        self._try_again_btn.hide()
        self._esc_hint.hide()
        self.hide()
        log.debug("Overlay cleared")

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # dim background
        painter.fillRect(self.rect(), QColor(0, 0, 0, config.OVERLAY_BG_ALPHA))

        if not self._elements:
            painter.end()
            return

        box_color = QColor(config.OVERLAY_BOX_COLOR)
        label_color = QColor(config.OVERLAY_LABEL_COLOR)
        expl_color = QColor(config.OVERLAY_EXPLANATION_COLOR)
        shadow_color = QColor(0, 0, 0, 200)

        label_font = QFont("Segoe UI", config.OVERLAY_FONT_SIZE, QFont.Weight.Bold)
        expl_font = QFont("Segoe UI", config.OVERLAY_FONT_SIZE - 1)

        for el in self._elements:
            bb = el["bounding_box"]
            x = int(bb["x"])
            y = int(bb["y"])
            w = int(bb["width"])
            h = int(bb["height"])
            label = el.get("label", "")
            explanation = el.get("explanation", "")

            # bounding box rectangle
            pen = QPen(box_color, config.OVERLAY_BOX_WIDTH)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x, y, w, h)

            # corner accent dots
            dot = 5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(box_color)
            for cx, cy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
                painter.drawEllipse(cx - dot, cy - dot, dot * 2, dot * 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # label above the box
            painter.setFont(label_font)
            lfm = QFontMetrics(label_font)
            lh = lfm.height()
            lx = x
            ly = max(y - lh - 4, lh + 2)

            painter.setPen(shadow_color)
            painter.drawText(lx + 1, ly + 1, label)
            painter.setPen(label_color)
            painter.drawText(lx, ly, label)

            # explanation below the box, word-wrapped
            if explanation:
                painter.setFont(expl_font)
                efm = QFontMetrics(expl_font)
                max_w = max(w, 260)
                lines = _wrap_text(explanation, efm, max_w)
                ey = y + h + efm.height() + 2
                for line in lines:
                    painter.setPen(shadow_color)
                    painter.drawText(x + 1, ey + 1, line)
                    painter.setPen(expl_color)
                    painter.drawText(x, ey, line)
                    ey += efm.height() + 2

        painter.end()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        for el in self._elements:
            bb = el["bounding_box"]
            rect = QRect(int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"]))
            if rect.contains(pos):
                return  # click was inside a box — don't close
        self.clear()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _wrap_text(text: str, fm: QFontMetrics, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if fm.horizontalAdvance(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
