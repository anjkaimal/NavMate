import json

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logger import get_logger

log = get_logger(__name__)

_POS_FILE    = ".navmate_dock_pos.json"
_CARD_W      = 200
_COLLAPSED_H = 44
_MARGIN      = 14
_QMAX        = 16_777_215

_EXPLAIN_IDLE_SS = """
QPushButton {
    background-color: rgba(0, 175, 215, 10);
    color: rgba(0, 207, 255, 200);
    border: 1px solid rgba(0, 207, 255, 75);
    border-radius: 10px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: rgba(0, 175, 215, 25);
    border-color: rgba(0, 207, 255, 180);
    color: #00CFFF;
}
"""

_EXPLAIN_ACTIVE_SS = """
QPushButton {
    background-color: rgba(200, 30, 30, 210);
    color: #FFFFFF;
    border: 2px solid rgba(255, 70, 70, 200);
    border-radius: 10px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: rgba(220, 50, 50, 220);
    border-color: rgba(255, 100, 100, 220);
}
"""


class AssistantDock(QWidget):
    ask_requested   = pyqtSignal()
    explain_toggled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._collapsed = False
        self._build_ui()
        self.adjustSize()
        self._load_position()

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
        self.setWindowOpacity(0.88)

        # ── Outer card ────────────────────────────────────────────────
        outer = QWidget(self)
        outer.setObjectName("dock_outer")
        outer.setStyleSheet("""
            QWidget#dock_outer {
                background-color: rgba(8, 10, 22, 240);
                border: 1px solid rgba(0, 207, 255, 65);
                border-radius: 16px;
            }
        """)

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(28)
        glow.setColor(QColor(0, 207, 255, 55))
        glow.setOffset(0, 0)
        outer.setGraphicsEffect(glow)

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(12, 10, 12, 12)
        outer_layout.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        dot = QLabel()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet("background: #00CFFF; border-radius: 4px;")
        header.addWidget(dot)

        title_lbl = QLabel("NavMate")
        title_lbl.setStyleSheet(
            "color: #00CFFF; font-size: 12px; font-weight: bold; background: transparent;"
        )
        header.addWidget(title_lbl)
        header.addStretch()

        self._collapse_btn = QPushButton("▼")
        self._collapse_btn.setFixedSize(22, 22)
        self._collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(0, 207, 255, 130);
                border: none;
                font-size: 10px;
            }
            QPushButton:hover { color: #00CFFF; }
        """)
        self._collapse_btn.clicked.connect(self._toggle_collapsed)
        header.addWidget(self._collapse_btn)

        outer_layout.addLayout(header)

        # ── Collapsible body ──────────────────────────────────────────
        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        self._ask_btn = QPushButton("🔍  Ask a Question")
        self._ask_btn.setFixedHeight(46)
        self._ask_btn.setStyleSheet("""
            QPushButton {
                background-color: #00CFFF;
                color: #020408;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover   { background-color: #33DAFF; }
            QPushButton:pressed { background-color: #009BBF; }
        """)
        self._ask_btn.clicked.connect(self.ask_requested)
        body_layout.addWidget(self._ask_btn)

        self._explain_btn = QPushButton("💡  Explain Mode")
        self._explain_btn.setFixedHeight(38)
        self._explain_btn.setStyleSheet(_EXPLAIN_IDLE_SS)
        self._explain_btn.clicked.connect(self.explain_toggled)
        body_layout.addWidget(self._explain_btn)

        self._hint = QLabel("Hover 2 s over anything to explain it")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet(
            "color: rgba(0, 207, 255, 140); font-size: 10px; background: transparent;"
        )
        sp = self._hint.sizePolicy()
        sp.setRetainSizeWhenHidden(False)
        self._hint.setSizePolicy(sp)
        self._hint.hide()
        body_layout.addWidget(self._hint)

        outer_layout.addWidget(self._body)

        # ── Root ──────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        root.addWidget(outer)

        self.setFixedWidth(_CARD_W + _MARGIN * 2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_explain_active(self, active: bool) -> None:
        self._explain_btn.setStyleSheet(
            _EXPLAIN_ACTIVE_SS if active else _EXPLAIN_IDLE_SS
        )
        self._explain_btn.setText(
            "🛑  Stop Explaining" if active else "💡  Explain Mode"
        )
        if active:
            self._hint.show()
        else:
            self._hint.hide()
        self._refresh_height()

    # ------------------------------------------------------------------
    # Collapse
    # ------------------------------------------------------------------

    def _toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._collapse_btn.setText("▲" if self._collapsed else "▼")
        self._body.setVisible(not self._collapsed)
        self._refresh_height()

    def _refresh_height(self) -> None:
        if self._collapsed:
            self.setFixedHeight(_COLLAPSED_H + _MARGIN * 2)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(_QMAX)
            self.adjustSize()

    # ------------------------------------------------------------------
    # Position persistence
    # ------------------------------------------------------------------

    def _load_position(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        default_x = screen.width()  - self.width()  - 20
        default_y = screen.height() - self.height() - 60
        try:
            with open(_POS_FILE) as f:
                data = json.load(f)
            x = max(0, min(data["x"], screen.width()  - self.width()))
            y = max(0, min(data["y"], screen.height() - self.height()))
            self.move(x, y)
        except Exception:
            self.move(default_x, max(0, default_y))

    def _save_position(self) -> None:
        try:
            with open(_POS_FILE, "w") as f:
                json.dump({"x": self.x(), "y": self.y()}, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._save_position()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Hover opacity
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setWindowOpacity(0.88)
        super().leaveEvent(event)
