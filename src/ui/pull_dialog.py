from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QPlainTextEdit, QFrame, QProgressBar,
)
from PyQt6.QtCore import Qt

from src.docker_client import DockerClient
from src.workers.pull_worker import PullWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"


class PullDialog(QDialog):
    def __init__(self, docker: DockerClient, parent=None):
        super().__init__(parent)
        self._docker = docker
        self._worker: PullWorker | None = None
        self.setWindowTitle("Pull Image")
        self.setFixedSize(560, 420)
        self.setStyleSheet(f"background: {BG};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(12)

        title = QLabel("Pull Docker Image")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        sub = QLabel("Enter an image name (e.g. nginx, ubuntu:22.04, python:3.11-slim)")
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(sub)

        # Input row
        input_row = QHBoxLayout()
        self._image_input = QLineEdit()
        self._image_input.setPlaceholderText("image:tag  (default tag: latest)")
        self._image_input.setStyleSheet(f"""
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        self._image_input.returnPressed.connect(self._start_pull)
        input_row.addWidget(self._image_input)

        self._pull_btn = QPushButton("Pull")
        self._pull_btn.setFixedHeight(36)
        self._pull_btn.setFixedWidth(80)
        self._pull_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pull_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {ACCENT}cc; }}
            QPushButton:disabled {{ background: #444; color: #777; }}
        """)
        self._pull_btn.clicked.connect(self._start_pull)
        input_row.addWidget(self._pull_btn)
        layout.addLayout(input_row)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {SURFACE};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {ACCENT};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._progress)

        # Log output
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-family: "Menlo", "Consolas", monospace;
            }}
        """)
        layout.addWidget(self._log, 1)

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedHeight(32)
        self._close_btn.setFixedWidth(80)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _start_pull(self):
        raw = self._image_input.text().strip()
        if not raw:
            return

        if ":" in raw:
            image, tag = raw.rsplit(":", 1)
        else:
            image, tag = raw, "latest"

        self._pull_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._log.clear()
        self._status_label.setText(f"Pulling {image}:{tag}…")
        self._log.appendPlainText(f"Pulling {image}:{tag}…\n")

        self._worker = PullWorker(self._docker, image, tag)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._log.appendPlainText(msg)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self):
        self._progress.setVisible(False)
        self._pull_btn.setEnabled(True)
        self._status_label.setText("Pull complete!")
        self._status_label.setStyleSheet(f"color: {GREEN}; font-size: 11px;")
        self._log.appendPlainText("\nDone.")

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._pull_btn.setEnabled(True)
        self._status_label.setText(f"Error: {msg}")
        self._status_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        self._log.appendPlainText(f"\nERROR: {msg}")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        super().closeEvent(event)
