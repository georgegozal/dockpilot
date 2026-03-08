"""App preferences dialog."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QLabel, QComboBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon

BG      = "#1e1e1e"
SURFACE = "#252526"
BORDER  = "#3e3e42"
TEXT    = "#cccccc"
ACCENT  = "#0078d4"

_LINUX          = sys.platform.startswith("linux")
_SYSTEM_DEFAULT = "(system default)"


def _list_icon_themes() -> list[str]:
    """Return sorted names of XDG icon themes installed on this system."""
    search_dirs = [
        Path.home() / ".icons",
        Path.home() / ".local" / "share" / "icons",
        Path("/usr/share/icons"),
        Path("/usr/local/share/icons"),
    ]
    seen: set[str] = set()
    for d in search_dirs:
        try:
            for entry in d.iterdir():
                if (
                    entry.is_dir()
                    and (entry / "index.theme").exists()
                    and not entry.name.startswith(".")
                    and not entry.name.lower().endswith("-cursor")
                    and entry.name.lower() != "default"
                ):
                    seen.add(entry.name)
        except OSError:
            pass
    return [_SYSTEM_DEFAULT] + sorted(seen, key=str.casefold)


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(380)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog   {{ background: {BG}; color: {TEXT}; }}
            QLabel    {{ color: {TEXT}; font-size: 13px; }}
            QComboBox {{
                background: {SURFACE}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; min-width: 160px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {SURFACE}; color: {TEXT};
                selection-background-color: {ACCENT};
                border: 1px solid {BORDER};
            }}
            QPushButton {{
                background: {SURFACE}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 4px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        self._settings = QSettings("DockPilot", "DockPilot")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(12)
        form.setContentsMargins(16, 16, 16, 16)

        if _LINUX:
            # Icon theme — Linux / freedesktop only
            self._icon_theme = QComboBox()
            themes = _list_icon_themes()
            self._icon_theme.addItems(themes)
            saved = self._settings.value("icon_theme", "")
            label = saved if saved else _SYSTEM_DEFAULT
            idx = self._icon_theme.findText(label)
            self._icon_theme.setCurrentIndex(max(0, idx))
            self._icon_theme.setToolTip(
                "Freedesktop icon theme for sidebar icons.\n"
                "Popular choices: Papirus, Adwaita, Breeze, Numix."
            )
            form.addRow("Icon theme:", self._icon_theme)
        else:
            # macOS — always uses emoji icons, nothing to configure yet
            note = QLabel("No preferences available for this platform.")
            note.setStyleSheet(f"color: #888888; font-size: 12px;")
            form.addRow(note)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(btns)

    def _apply(self):
        if not _LINUX:
            return
        chosen = self._icon_theme.currentText()
        theme_name = "" if chosen == _SYSTEM_DEFAULT else chosen
        self._settings.setValue("icon_theme", theme_name)
        if theme_name:
            QIcon.setThemeName(theme_name)

        # Tell the sidebar to refresh all nav button icons
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_icons"):
            parent.refresh_icons()

    def _save(self):
        self._apply()
        self.accept()
