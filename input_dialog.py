from PyQt6.QtCore import Qt, pyqtSignal
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


class QueryDialog(QWidget):
    query_submitted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

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
            QLabel {
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
            QPushButton#go_btn:hover  { background-color: #00FF99; }
            QPushButton#go_btn:pressed { background-color: #009955; }
            QPushButton#close_btn {
                background-color: transparent;
                color: #555555;
                border: none;
                font-size: 18px;
                padding: 0px 8px;
            }
            QPushButton#close_btn:hover { color: #CCCCCC; }
        """)

        outer = QWidget(self)
        outer.setObjectName("outer")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(16, 12, 16, 12)
        outer_layout.setSpacing(8)

        hint = QLabel("NavMate  ·  What do you want to do?")
        outer_layout.addWidget(hint)

        self.input = QLineEdit()
        self.input.setPlaceholderText('e.g. "How do I mute myself in Zoom?"')
        self.input.returnPressed.connect(self._submit)
        outer_layout.addWidget(self.input)

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

    def show_centered(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
        self.input.clear()
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
