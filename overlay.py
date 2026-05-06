from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
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
        # Dimensions of the image the AI analysed.
        # Scale is computed fresh in paintEvent from self.width()/height() so it
        # always reflects the true rendered window size, not a pre-captured value.
        self._ai_img_w: int = 0
        self._ai_img_h: int = 0
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
                background-color: #1A4FD6;
                color: #FFFFFF;
                border: 2px solid #5AABFF;
                border-radius: 8px;
                padding: 9px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover   { background-color: #1E6FEB; border-color: #FFFFFF; }
            QPushButton:pressed { background-color: #0F3199; }
        """)
        self._try_again_btn.clicked.connect(self.try_again_requested)
        self._try_again_btn.hide()

        self._esc_hint = QPushButton("Press Esc to close", self)
        self._esc_hint.setStyleSheet("""
            QPushButton {
                background-color: rgba(10, 20, 60, 160);
                color: rgba(200, 210, 255, 200);
                border: 1px solid rgba(90, 171, 255, 80);
                border-radius: 4px;
                font-size: 12px;
                padding: 3px 10px;
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

        # Use the full logical screen geometry — do NOT call showFullScreen() because
        # it can apply internal geometry offsets on Windows with DPI scaling, shifting
        # every drawn coordinate by an unexpected amount.  Explicit setGeometry() gives
        # us a window whose local (0,0) maps exactly to screen (0,0), and whose
        # self.width()/height() in paintEvent match what we intend.
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        m = 16
        bw, bh = 140, 40
        self._try_again_btn.setGeometry(
            screen.width() - bw - m, screen.height() - bh - m, bw, bh
        )
        self._try_again_btn.show()
        self._try_again_btn.raise_()

        hw = 180
        self._esc_hint.setGeometry(
            screen.width() // 2 - hw // 2, screen.height() - 30, hw, 24
        )
        self._esc_hint.show()
        self._esc_hint.raise_()

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

        # Semi-transparent dim over the whole screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, config.OVERLAY_BG_ALPHA))

        if not self._elements or self._ai_img_w <= 0 or self._ai_img_h <= 0:
            painter.end()
            return

        # Compute scale here, from the widget's ACTUAL rendered dimensions.
        # self.width()/height() is the ground truth — it reflects exactly the
        # pixel space that QPainter uses for this widget.  Dividing by the AI
        # image dimensions gives the correct map from AI-coordinate → screen-coordinate,
        # handling both image resize and Windows DPI scaling in one step.
        scale_x = self.width()  / self._ai_img_w
        scale_y = self.height() / self._ai_img_h
        log.debug(f"Paint scale: {scale_x:.4f}×{scale_y:.4f}  "
                  f"(widget {self.width()}×{self.height()}, "
                  f"ai-img {self._ai_img_w}×{self._ai_img_h})")

        label_font = QFont("Segoe UI", config.OVERLAY_LABEL_FONT_SIZE, QFont.Weight.Bold)
        box_color    = QColor(config.OVERLAY_BOX_COLOR)
        corner_color = QColor(config.OVERLAY_CORNER_COLOR)

        instruction = ""
        for el in self._elements:
            bb = el["bounding_box"]
            x  = round(bb["x"]      * scale_x)
            y  = round(bb["y"]      * scale_y)
            w  = round(bb["width"]  * scale_x)
            h  = round(bb["height"] * scale_y)

            self._draw_box(painter, x, y, w, h, box_color, corner_color)
            self._draw_label(painter, x, y, w, el.get("label", ""), label_font)
            if not instruction:
                instruction = (el.get("voice_instruction")
                               or el.get("instruction")
                               or el.get("explanation", ""))

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
        border: QColor,
        corner: QColor,
    ) -> None:
        r, g, b, a = config.OVERLAY_BOX_FILL
        p.fillRect(x, y, w, h, QColor(r, g, b, a))

        p.setPen(QPen(border, config.OVERLAY_BOX_WIDTH))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x, y, w, h)

        dot = 6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(corner))
        for cx, cy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
            p.drawEllipse(cx - dot, cy - dot, dot * 2, dot * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_label(
        self,
        p: QPainter,
        x: int, y: int, box_w: int,
        text: str,
        font: QFont,
    ) -> None:
        if not text:
            return
        p.setFont(font)
        fm = QFontMetrics(font)

        pad_h, pad_v = 10, 5
        badge_w = fm.horizontalAdvance(text) + pad_h * 2
        badge_h = fm.height() + pad_v * 2

        # Centre the label horizontally over the box; keep it on screen.
        badge_x = x + (box_w - badge_w) // 2
        badge_x = max(0, min(self.width() - badge_w, badge_x))
        badge_y = max(0, y - badge_h - 8)

        r, g, b = _hex_to_rgb(config.OVERLAY_LABEL_BG)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(r, g, b, 235)))
        p.drawRoundedRect(
            badge_x, badge_y, badge_w, badge_h,
            config.OVERLAY_BADGE_RADIUS, config.OVERLAY_BADGE_RADIUS,
        )

        p.setPen(QColor(config.OVERLAY_LABEL_COLOR))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawText(badge_x + pad_h, badge_y + pad_v + fm.ascent(), text)

    def _draw_instruction_bar(self, p: QPainter, text: str) -> None:
        """Render a centered voice-instruction caption near the bottom of the screen."""
        font = QFont("Segoe UI", config.OVERLAY_INSTR_FONT_SIZE)
        p.setFont(font)
        fm = QFontMetrics(font)

        sw, sh = self.width(), self.height()
        max_text_w = int(sw * 0.75)
        lines = _wrap_text(text, fm, max_text_w)
        if not lines:
            return

        pad_h, pad_v = 20, 10
        line_h = fm.height() + 3
        text_w = max(fm.horizontalAdvance(ln) for ln in lines)
        bar_w = text_w + pad_h * 2
        bar_h = len(lines) * line_h + pad_v * 2

        # Sits above the Esc hint (30px) with an 18px gap, horizontally centered.
        bar_x = (sw - bar_w) // 2
        bar_y = sh - 30 - 18 - bar_h

        r, g, b, a = config.OVERLAY_EXPL_BG
        p.setPen(QPen(QColor(config.OVERLAY_EXPL_BORDER), 1))
        p.setBrush(QBrush(QColor(r, g, b, a)))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 10, 10)

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
                return  # click inside a labelled box — keep overlay open
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


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
