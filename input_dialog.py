from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import voice_input
from logger import get_logger

log = get_logger(__name__)

_HINT_DEFAULT = "What would you like to do?"

_MIC_IDLE_SS = ""   # reset to class stylesheet

_MIC_PULSE_A = """QPushButton {
    background-color: rgba(220, 45, 45, 215);
    color: #FFFFFF;
    border: 2px solid rgba(255, 80, 80, 200);
    border-radius: 10px;
    font-size: 15px;
    font-weight: bold;
    padding: 12px 20px;
}"""
_MIC_PULSE_B = """QPushButton {
    background-color: rgba(145, 18, 18, 175);
    color: rgba(255, 160, 160, 220);
    border: 1px solid rgba(180, 40, 40, 160);
    border-radius: 10px;
    font-size: 15px;
    font-weight: bold;
    padding: 12px 20px;
}"""


class _MicBridge(QObject):
    """Carry callbacks from the mic daemon thread → Qt main thread."""
    ready  = pyqtSignal()
    result = pyqtSignal(str)
    error  = pyqtSignal(str)


class QueryDialog(QWidget):
    query_submitted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._mic_bridge   = _MicBridge()
        self._pulse_timer  = QTimer(self)
        self._pulse_timer.setInterval(450)
        self._pulse_state  = False
        self._build_ui()
        self._wire_signals()

    def _wire_signals(self) -> None:
        self._mic_bridge.ready.connect(self._on_mic_ready)
        self._mic_bridge.result.connect(self._on_mic_result)
        self._mic_bridge.error.connect(self._on_mic_error)
        self._pulse_timer.timeout.connect(self._pulse_step)

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)

        # ── Outer card ────────────────────────────────────────────────
        outer = QWidget(self)
        outer.setObjectName("outer")
        outer.setStyleSheet("""
            QWidget#outer {
                background-color: rgba(9, 11, 26, 252);
                border: 1px solid rgba(0, 207, 255, 60);
                border-radius: 18px;
            }
        """)

        # Cyan glow halo around card
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(38)
        glow.setColor(QColor(0, 207, 255, 55))
        glow.setOffset(0, 0)
        outer.setGraphicsEffect(glow)

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(22, 18, 22, 20)
        outer_layout.setSpacing(10)

        # ── Header row: logo dot + title + close ──────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        logo_dot = QLabel()
        logo_dot.setFixedSize(12, 12)
        logo_dot.setStyleSheet(
            "background-color: #00CFFF; border-radius: 6px;"
        )
        header.addWidget(logo_dot)

        title = QLabel("NavMate")
        title.setStyleSheet(
            "color: #00CFFF; font-size: 15px; font-weight: bold; background: transparent;"
        )
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("close_btn")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(100, 130, 190, 180);
                border: none;
                font-size: 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(255, 70, 70, 40);
            }
        """)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        outer_layout.addLayout(header)

        # ── Hint label ────────────────────────────────────────────────
        self._hint = QLabel(_HINT_DEFAULT)
        self._hint.setStyleSheet(
            "color: rgba(160, 200, 255, 200); font-size: 14px; background: transparent;"
        )
        outer_layout.addWidget(self._hint)

        # ── Input field ───────────────────────────────────────────────
        self.input = QLineEdit()
        self.input.setPlaceholderText('e.g.  "How do I mute myself in Zoom?"')
        self.input.setFixedHeight(52)
        self.input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 7);
                color: #FFFFFF;
                border: 1px solid rgba(0, 207, 255, 50);
                border-radius: 10px;
                padding: 0px 16px;
                font-size: 16px;
                selection-background-color: #00CFFF;
                selection-color: #000000;
            }
            QLineEdit:focus {
                border: 1px solid rgba(0, 207, 255, 190);
                background-color: rgba(0, 175, 215, 10);
            }
        """)
        self.input.returnPressed.connect(self._submit)
        outer_layout.addWidget(self.input)

        # ── Button row: [Speak]  [Go] ──────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(12)

        self.mic_btn = QPushButton("🎤   Speak")
        self.mic_btn.setObjectName("mic_btn")
        self.mic_btn.setFixedHeight(46)
        self.mic_btn.setStyleSheet("""
            QPushButton#mic_btn {
                background-color: rgba(0, 175, 215, 12);
                color: rgba(0, 207, 255, 210);
                border: 1px solid rgba(0, 207, 255, 80);
                border-radius: 10px;
                font-size: 15px;
                font-weight: bold;
                padding: 0px 20px;
            }
            QPushButton#mic_btn:hover {
                background-color: rgba(0, 175, 215, 28);
                border-color: rgba(0, 207, 255, 190);
                color: #00CFFF;
            }
            QPushButton#mic_btn:disabled {
                color: rgba(60, 80, 110, 180);
                border-color: rgba(40, 60, 90, 120);
            }
        """)
        self.mic_btn.setToolTip("Click to speak your query")
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        btn_row.addWidget(self.mic_btn, 1)

        self.go_btn = QPushButton("Go  →")
        self.go_btn.setObjectName("go_btn")
        self.go_btn.setFixedHeight(46)
        self.go_btn.setStyleSheet("""
            QPushButton#go_btn {
                background-color: #00CFFF;
                color: #020408;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: bold;
                padding: 0px 28px;
            }
            QPushButton#go_btn:hover   { background-color: #33DAFF; }
            QPushButton#go_btn:pressed { background-color: #009BBF; }
        """)
        self.go_btn.clicked.connect(self._submit)
        btn_row.addWidget(self.go_btn, 1)

        outer_layout.addLayout(btn_row)

        # ── Root layout with margins for glow to show ─────────────────
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(22, 22, 22, 22)
        root_layout.addWidget(outer)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Mic state machine  (all handlers run on Qt main thread via bridge)
    # ------------------------------------------------------------------

    def _on_mic_clicked(self) -> None:
        self.mic_btn.setEnabled(False)
        self._hint.setText("Calibrating microphone…")
        voice_input.start_listening(
            on_ready=self._mic_bridge.ready.emit,
            on_result=self._mic_bridge.result.emit,
            on_error=self._mic_bridge.error.emit,
        )

    def _on_mic_ready(self) -> None:
        self._hint.setText("🔴  Listening — speak your question now")
        self._pulse_state = False
        self._pulse_timer.start()

    def _on_mic_result(self, text: str) -> None:
        self._reset_mic_ui()
        log.debug(f"Voice query: {text!r}")
        self.input.setText(text)
        self._submit()

    def _on_mic_error(self, msg: str) -> None:
        self._reset_mic_ui()
        self._hint.setText(f"⚠   {msg}")
        QTimer.singleShot(2800, lambda: self._hint.setText(_HINT_DEFAULT))

    def _reset_mic_ui(self) -> None:
        self._pulse_timer.stop()
        self.mic_btn.setEnabled(True)
        self.mic_btn.setStyleSheet(_MIC_IDLE_SS)
        self._hint.setText(_HINT_DEFAULT)

    def _pulse_step(self) -> None:
        self._pulse_state = not self._pulse_state
        self.mic_btn.setStyleSheet(_MIC_PULSE_A if self._pulse_state else _MIC_PULSE_B)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_centered(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
        self.input.clear()
        self._reset_mic_ui()
        self.show()
        self.activateWindow()
        self.input.setFocus()

    def _submit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.hide()
            self.query_submitted.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
