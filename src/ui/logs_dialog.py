from __future__ import annotations
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QPlainTextEdit, QFrame, QLineEdit, QCheckBox,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat

from src.docker_client import DockerClient
from src.workers.logs_worker import LogsWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"
YELLOW   = "#ffb900"

# Strip ANSI escape sequences
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]|\x1b\[?[0-9;]*[A-Za-z]|\x1b\].*?\x07")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class LogsDialog(QDialog):
    def __init__(self, docker: DockerClient, container_id: str, parent=None):
        super().__init__(parent)
        self._docker = docker
        self._container_id = container_id
        self._worker: LogsWorker | None = None
        self._following = True

        c = docker.get_container(container_id)
        name = c.name if c else container_id[:12]
        self.setWindowTitle(f"Logs — {name}")
        self.resize(1000, 650)
        self.setStyleSheet(f"background: {BG};")
        self._build_ui()
        self._start_logs(500)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(8)

        tail_lbl = QLabel("Tail:")
        tail_lbl.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        tb.addWidget(tail_lbl)

        self._tail_spin = QSpinBox()
        self._tail_spin.setRange(10, 10000)
        self._tail_spin.setValue(500)
        self._tail_spin.setFixedWidth(80)
        self._tail_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
            }}
        """)
        tb.addWidget(self._tail_spin)

        self._follow_check = QCheckBox("Follow")
        self._follow_check.setChecked(True)
        self._follow_check.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        self._follow_check.toggled.connect(self._on_follow_toggle)
        tb.addWidget(self._follow_check)

        reload_btn = QPushButton("Reload")
        reload_btn.setFixedHeight(28)
        reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reload_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 0 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        reload_btn.clicked.connect(self._reload)
        tb.addWidget(reload_btn)

        tb.addStretch()

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search in logs…")
        self._search_input.setFixedWidth(220)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
        """)
        self._search_input.textChanged.connect(self._search_changed)
        tb.addWidget(self._search_input)

        self._search_prev = QPushButton("")
        self._search_next = QPushButton("")
        for btn, ch in [(self._search_prev, ""), (self._search_next, "")]:
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {BG};
                    color: {TEXT};
                    border: 1px solid {BORDER};
                    border-radius: 4px;
                    font-size: 14px;
                }}
                QPushButton:hover {{ background: #2a2d2e; }}
            """)
        self._search_prev.setText("↑")
        self._search_next.setText("↓")
        self._search_prev.clicked.connect(self._find_prev)
        self._search_next.clicked.connect(self._find_next)
        tb.addWidget(self._search_prev)
        tb.addWidget(self._search_next)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(28)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 0 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        clear_btn.clicked.connect(self._clear)
        tb.addWidget(clear_btn)

        layout.addWidget(toolbar)

        # Log view
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(50000)
        font = QFont("Menlo, Monaco, Consolas, Courier New", 12)
        self._log_view.setFont(font)
        self._log_view.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {BG};
                color: {TEXT};
                border: none;
                padding: 8px;
                selection-background-color: {ACCENT}55;
            }}
        """)
        layout.addWidget(self._log_view, 1)

        # Status bar
        self._status_label = QLabel("Connecting…")
        self._status_label.setStyleSheet(f"""
            color: {TEXT_DIM};
            font-size: 11px;
            padding: 4px 12px;
            background: {SURFACE};
            border-top: 1px solid {BORDER};
        """)
        layout.addWidget(self._status_label)

    def _start_logs(self, tail: int):
        self._stop_worker()
        self._log_view.clear()
        self._worker = LogsWorker(self._docker, self._container_id, tail=tail)
        self._worker.new_data.connect(self._append_log)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        self._status_label.setText("Streaming logs…")

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._worker = None

    def _append_log(self, text: str):
        clean = _strip_ansi(text).rstrip("\n")
        if not clean:
            return
        self._log_view.appendPlainText(clean)
        if self._following:
            self._log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _on_error(self, msg: str):
        self._status_label.setText(f"Error: {msg}")

    def _on_follow_toggle(self, checked: bool):
        self._following = checked
        if checked:
            self._log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _reload(self):
        self._start_logs(self._tail_spin.value())

    def _clear(self):
        self._log_view.clear()

    # ── Search ──────────────────────────────────────────────────────────

    def _search_changed(self, text: str):
        if not text:
            # Clear any highlights by re-setting the document palette
            self._log_view.setExtraSelections([])
        else:
            self._highlight_all(text)

    def _highlight_all(self, text: str):
        from PyQt6.QtWidgets import QTextEdit
        extra = []
        doc = self._log_view.document()
        cursor = doc.find(text)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#856404"))
        while not cursor.isNull():
            sel = QPlainTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            extra.append(sel)
            cursor = doc.find(text, cursor)
        self._log_view.setExtraSelections(extra)

    def _find_next(self):
        text = self._search_input.text()
        if text:
            self._log_view.find(text)

    def _find_prev(self):
        from PyQt6.QtGui import QTextDocument
        text = self._search_input.text()
        if text:
            self._log_view.find(text, QTextDocument.FindFlag.FindBackward)

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

