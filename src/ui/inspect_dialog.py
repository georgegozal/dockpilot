from __future__ import annotations
import json

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor
import re

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"

# ── Basic JSON syntax highlighter ─────────────────────────────────────────────

class JsonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(700)
            return f

        # Keys
        self._rules.append((re.compile(r'"[^"\\]*"(?=\s*:)'), fmt("#9cdcfe")))
        # String values
        self._rules.append((re.compile(r':\s*"[^"\\]*"'), fmt("#ce9178")))
        # Numbers
        self._rules.append((re.compile(r'\b\d+(\.\d+)?\b'), fmt("#b5cea8")))
        # Booleans / null
        self._rules.append((re.compile(r'\b(true|false|null)\b'), fmt("#569cd6", bold=True)))
        # Brackets
        self._rules.append((re.compile(r'[{}\[\]]'), fmt("#ffd700")))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class InspectDialog(QDialog):
    def __init__(self, title: str, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 600)
        self.setStyleSheet(f"background: {BG};")
        self._data = data
        self._json_text = json.dumps(data, indent=2, default=str)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 6, 12, 6)
        tb.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setFixedWidth(200)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
        """)
        self._search.textChanged.connect(self._find)
        tb.addWidget(self._search)
        tb.addStretch()

        copy_btn = QPushButton("Copy JSON")
        copy_btn.setFixedHeight(28)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {ACCENT}cc; }}
        """)
        copy_btn.clicked.connect(self._copy)
        tb.addWidget(copy_btn)
        layout.addWidget(toolbar)

        # Content
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setFont(QFont("Menlo, Monaco, Consolas, Courier New", 12))
        self._editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {BG};
                color: {TEXT};
                border: none;
                padding: 8px;
            }}
        """)
        self._editor.setPlainText(self._json_text)
        JsonHighlighter(self._editor.document())
        layout.addWidget(self._editor, 1)

    def _find(self, text: str):
        if text:
            self._editor.find(text)

    def _copy(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._json_text)
