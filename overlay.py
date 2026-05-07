import math

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

import config
from logger import get_logger

log = get_logger(__name__)

# Pulse cycle: ~1.8 s at 50 ms intervals (20 fps)
_PULSE_SPEED   = 0.175
_BRACKET_LEN   = 20    # px — length of each corner bracket arm
_BRACKET_WIDTH = 3     # px


class OverlayWindow(QWidget):
    try_again_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._elements: list[dict] = []
        self._ai_img_w: int = 0
        self._ai_img_h: int = 0

        self._pulse_frame = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._tick)

        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._try_again_btn = QPushButton("↺   Try Again", self)
        self._try_again_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 150, 200, 18);
                color: #00CFFF;
                border: 1px solid rgba(0, 207, 255, 100);
                border-radius: 10px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover   {{
                background-color: rgba(0, 175, 215, 38);
                border-color: #00CFFF;
            }}
            QPushButton:pressed {{ background-color: rgba(0, 110, 150, 40); }}
        """)
        self._try_again_btn.clicked.connect(self.try_again_requested)
        self._try_again_btn.hide()

        self._esc_hint = QPushButton("Esc to close", self)
        self._esc_hint.setStyleSheet("""
            QPushButton {
                background-color: rgba(6, 9, 22, 160);
                color: rgba(0, 207, 255, 120);
                border: 1px solid rgba(0, 207, 255, 35);
                border-radius: 5px;
                font-size: 12px;
                padding: 4px 14px;
            }
        """)
        self._esc_hint.setEnabled(False)
        self._esc_hint.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_elements(
        self,
        elements: list[dict],
        ai_img_w: int = 0,
        ai_img_h: int = 0,
    ) -> None:
        self._elements = elements
        self._ai_img_w = ai_img_w
        self._ai_img_h = ai_img_h

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        m = 18
        bw, bh = 150, 42
        self._try_again_btn.setGeometry(
            screen.width() - bw - m, screen.height() - bh - m, bw, bh
        )
        self._try_again_btn.show()
        self._try_again_btn.raise_()

        hw = 160
        self._esc_hint.setGeometry(
            screen.width() // 2 - hw // 2, screen.height() - 32, hw, 22
        )
        self._esc_hint.show()
        self._esc_hint.raise_()

        self._pulse_frame = 0
        self._pulse_timer.start()

        self.show()
        self.raise_()
        self.activateWindow()
        self.update()
        log.debug(
            f"Overlay: {len(elements)} elements, "
            f"ai-img {ai_img_w}×{ai_img_h}, "
            f"window {self.width()}×{self.height()}"
        )

    def clear(self) -> None:
        self._pulse_timer.stop()
        self._elements = []
        self._try_again_btn.hide()
        self._esc_hint.hide()
        self.hide()
        log.debug("Overlay cleared")

    # ------------------------------------------------------------------
    # Animation tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._pulse_frame += 1
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Semi-transparent screen dim
        painter.fillRect(self.rect(), QColor(0, 0, 0, config.OVERLAY_BG_ALPHA))

        if not self._elements or self._ai_img_w <= 0 or self._ai_img_h <= 0:
            painter.end()
            return

        scale_x = self.width()  / self._ai_img_w
        scale_y = self.height() / self._ai_img_h
        log.debug(
            f"Paint scale: {scale_x:.4f}×{scale_y:.4f}  "
            f"(widget {self.width()}×{self.height()}, "
            f"ai-img {self._ai_img_w}×{self._ai_img_h})"
        )

        pulse = (math.sin(self._pulse_frame * _PULSE_SPEED) + 1) / 2   # 0–1

        label_font = QFont(
            "Segoe UI", config.OVERLAY_LABEL_FONT_SIZE, QFont.Weight.Bold
        )

        instruction = ""
        for el in self._elements:
            bb = el["bounding_box"]
            x  = round(bb["x"]      * scale_x)
            y  = round(bb["y"]      * scale_y)
            w  = round(bb["width"]  * scale_x)
            h  = round(bb["height"] * scale_y)

            self._draw_box(painter, x, y, w, h, pulse)
            self._draw_label(painter, x, y, w, el.get("label", ""), label_font, pulse)
            if not instruction:
                instruction = (
                    el.get("voice_instruction")
                    or el.get("instruction")
                    or el.get("explanation", "")
                )

        if instruction:
            self._draw_instruction_bar(painter, instruction)

        painter.end()

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_box(
        self,
        p: QPainter,
        x: int, y: int, w: int, h: int,
        pulse: float,
    ) -> None:
        # Subtle fill
        r, g, b, a = config.OVERLAY_BOX_FILL
        p.fillRect(x, y, w, h, QColor(r, g, b, a))

        # Outer glow rings — fade in/out with pulse
        glow_intensity = 0.5 + pulse * 0.5
        for offset, base_alpha in [(5, 28), (10, 14), (16, 7)]:
            ga = int(base_alpha * glow_intensity)
            p.setPen(QPen(QColor(0, 207, 255, ga), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(x - offset, y - offset, w + offset * 2, h + offset * 2, 6, 6)

        # Main border
        border_alpha = int(100 + pulse * 155)
        p.setPen(QPen(QColor(0, 207, 255, border_alpha), config.OVERLAY_BOX_WIDTH))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(x, y, w, h, 4, 4)

        # Corner brackets — brighter and sharper than the border
        bracket_alpha = int(190 + pulse * 65)
        pen = QPen(
            QColor(0, 220, 255, bracket_alpha),
            _BRACKET_WIDTH,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        bl = _BRACKET_LEN

        # Top-left
        p.drawLine(x, y + bl, x, y);  p.drawLine(x, y, x + bl, y)
        # Top-right
        p.drawLine(x + w - bl, y, x + w, y);  p.drawLine(x + w, y, x + w, y + bl)
        # Bottom-left
        p.drawLine(x, y + h - bl, x, y + h);  p.drawLine(x, y + h, x + bl, y + h)
        # Bottom-right
        p.drawLine(x + w - bl, y + h, x + w, y + h);  p.drawLine(x + w, y + h, x + w, y + h - bl)

    def _draw_label(
        self,
        p: QPainter,
        x: int, y: int, box_w: int,
        text: str,
        font: QFont,
        pulse: float,
    ) -> None:
        if not text:
            return
        p.setFont(font)
        fm = QFontMetrics(font)

        pad_h, pad_v = 14, 6
        badge_w = fm.horizontalAdvance(text) + pad_h * 2
        badge_h = fm.height() + pad_v * 2

        badge_x = x + (box_w - badge_w) // 2
        badge_x = max(0, min(self.width() - badge_w, badge_x))
        badge_y = max(0, y - badge_h - 10)

        # Badge background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(5, 10, 28, 240)))
        p.drawRoundedRect(
            badge_x, badge_y, badge_w, badge_h,
            config.OVERLAY_BADGE_RADIUS, config.OVERLAY_BADGE_RADIUS,
        )

        # Badge border — pulses with target box
        border_alpha = int(100 + pulse * 130)
        p.setPen(QPen(QColor(0, 207, 255, border_alpha), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(
            badge_x, badge_y, badge_w, badge_h,
            config.OVERLAY_BADGE_RADIUS, config.OVERLAY_BADGE_RADIUS,
        )

        # Label text
        p.setPen(QColor(config.OVERLAY_LABEL_COLOR))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawText(badge_x + pad_h, badge_y + pad_v + fm.ascent(), text)

    def _draw_instruction_bar(self, p: QPainter, text: str) -> None:
        font = QFont("Segoe UI", config.OVERLAY_INSTR_FONT_SIZE)
        p.setFont(font)
        fm = QFontMetrics(font)

        sw, sh = self.width(), self.height()
        max_text_w = int(sw * 0.80)
        lines = _wrap_text(text, fm, max_text_w)
        if not lines:
            return

        pad_h, pad_v = 28, 14
        line_h = fm.height() + 4
        text_w = max(fm.horizontalAdvance(ln) for ln in lines)
        bar_w  = text_w + pad_h * 2
        bar_h  = len(lines) * line_h + pad_v * 2

        bar_x = (sw - bar_w) // 2
        bar_y = sh - 42 - bar_h   # sits above Esc hint

        # Background
        r, g, b, a = config.OVERLAY_EXPL_BG
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(r, g, b, a)))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 12, 12)

        # Border
        p.setPen(QPen(QColor(config.OVERLAY_EXPL_BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 12, 12)

        # Text
        p.setPen(QColor(config.OVERLAY_EXPL_COLOR))
        p.setBrush(Qt.BrushStyle.NoBrush)
        ty = bar_y + pad_v + fm.ascent()
        for line in lines:
            lx = bar_x + (bar_w - fm.horizontalAdvance(line)) // 2
            p.drawText(lx, ty, line)
            ty += line_h

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._ai_img_w <= 0 or self._ai_img_h <= 0:
            self.clear()
            return
        scale_x = self.width()  / self._ai_img_w
        scale_y = self.height() / self._ai_img_h
        pos = event.position().toPoint()
        for el in self._elements:
            bb = el["bounding_box"]
            rect = QRect(
                round(bb["x"]      * scale_x),
                round(bb["y"]      * scale_y),
                round(bb["width"]  * scale_x),
                round(bb["height"] * scale_y),
            )
            if rect.contains(pos):
                return
        self.clear()


# ------------------------------------------------------------------
# Module helpers
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
