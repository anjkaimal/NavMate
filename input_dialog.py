from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
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

_HINT_DEFAULT = "NavMate  ·  What do you want to do?"

_MIC_IDLE_SS = ""   # reset to class stylesheet

# Pulsing red styles alternated by QTimer while recording
_MIC_PULSE_A = """QPushButton {
    background-color: rgba(210, 40, 40, 220);
    color: #FFFFFF;
    border: 2px solid #FF6060;
    border-radius: 7px;
    font-size: 16px;
}"""
_MIC_PULSE_B = """QPushButton {
    background-color: rgba(150, 20, 20, 180);
    color: #FF9999;
    border: 1px solid #993333;
    border-radius: 7px;
    font-size: 16px;
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
        self._mic_bridge = _MicBridge()
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(450)
        self._pulse_state = False
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
        self.setFixedWidth(520)

        self.setStyleSheet("""
            QWidget#outer {
                background-color: rgba(22, 22, 28, 230);
                border: 1px solid rgba(0, 255, 153, 80);
                border-radius: 12px;
            }
            QLabel#hint {
                color: #888888;
                font-size: 11px;
                background: transparent;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 12);
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 7px;
                padding: 9px 12px;
                font-size: 14px;
                selection-background-color: #00CC77;
            }
            QLineEdit:focus { border: 1px solid #00CC77; }
            QPushButton#go_btn {
                background-color: #00CC77;
                color: #000000;
                border: none;
                border-radius: 7px;
                padding: 9px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#go_btn:hover   { background-color: #00FF99; }
            QPushButton#go_btn:pressed { background-color: #009955; }
            QPushButton#close_btn {
                background-color: transparent;
                color: #555555;
                border: none;
                font-size: 18px;
                padding: 0px 8px;
            }
            QPushButton#close_btn:hover { color: #CCCCCC; }
            QPushButton#mic_btn {
                background-color: rgba(255, 255, 255, 8);
                color: #888888;
                border: 1px solid #444444;
                border-radius: 7px;
                font-size: 16px;
            }
            QPushButton#mic_btn:hover {
                background-color: rgba(255, 255, 255, 18);
                color: #FFFFFF;
                border-color: #888888;
            }
            QPushButton#mic_btn:disabled {
                color: #333333;
                border-color: #2a2a2a;
            }
        """)

        outer = QWidget(self)
        outer.setObjectName("outer")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(16, 12, 16, 12)
        outer_layout.setSpacing(8)

        self._hint = QLabel(_HINT_DEFAULT)
        self._hint.setObjectName("hint")
        outer_layout.addWidget(self._hint)

        # Input row: [🎤 mic button] [text field]
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("mic_btn")
        self.mic_btn.setFixedSize(38, 38)
        self.mic_btn.setToolTip("Speak your query")
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self.mic_btn)

        self.input = QLineEdit()
        self.input.setPlaceholderText('e.g. "How do I mute myself in Zoom?"')
        self.input.returnPressed.connect(self._submit)
        input_row.addWidget(self.input)

        outer_layout.addLayout(input_row)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()

        self.go_btn = QPushButton("Go")
        self.go_btn.setObjectName("go_btn")
        self.go_btn.clicked.connect(self._submit)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("close_btn")
        self.close_btn.clicked.connect(self.hide)

        btn_row.addWidget(self.go_btn)
        btn_row.addWidget(self.close_btn)
        outer_layout.addLayout(btn_row)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Mic state machine  (all handlers run on Qt main thread via bridge)
    # ------------------------------------------------------------------

    def _on_mic_clicked(self) -> None:
        self.mic_btn.setEnabled(False)
        self._hint.setText("Calibrating mic…")
        voice_input.start_listening(
            on_ready=self._mic_bridge.ready.emit,
            on_result=self._mic_bridge.result.emit,
            on_error=self._mic_bridge.error.emit,
        )

    def _on_mic_ready(self) -> None:
        self._hint.setText("🔴  Listening — speak now")
        self._pulse_state = False
        self._pulse_timer.start()

    def _on_mic_result(self, text: str) -> None:
        self._reset_mic_ui()
        log.debug(f"Voice query: {text!r}")
        self.input.setText(text)
        self._submit()   # voice input goes straight through; typing requires explicit Go

    def _on_mic_error(self, msg: str) -> None:
        self._reset_mic_ui()
        self._hint.setText(f"⚠  {msg}")
        QTimer.singleShot(2500, lambda: self._hint.setText(_HINT_DEFAULT))

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
