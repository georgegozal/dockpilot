"""App preferences dialog."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QLabel, QComboBox, QSpinBox, QGroupBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon

BG      = "#1e1e1e"
SURFACE = "#252526"
BORDER  = "#3e3e42"
TEXT    = "#cccccc"
TEXT_DIM = "#888888"
ACCENT  = "#0078d4"

_LINUX          = sys.platform.startswith("linux")
_MACOS          = sys.platform == "darwin"
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


def _spin_style() -> str:
    return f"""
        QSpinBox {{
            background: {SURFACE}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px;
            padding: 4px 8px; font-size: 12px; min-width: 80px;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 16px; background: {SURFACE}; border: none;
        }}
    """


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog   {{ background: {BG}; color: {TEXT}; }}
            QLabel    {{ color: {TEXT}; font-size: 13px; }}
            QGroupBox {{
                color: {TEXT}; font-size: 13px; font-weight: bold;
                border: 1px solid {BORDER}; border-radius: 6px;
                margin-top: 10px; padding-top: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
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
        self._icon_theme: QComboBox | None = None
        self._cpu: QSpinBox | None = None
        self._memory: QSpinBox | None = None
        self._disk: QSpinBox | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        if _MACOS:
            layout.addWidget(self._build_colima_group())

        if _LINUX:
            layout.addWidget(self._build_linux_group())

        if not _MACOS and not _LINUX:
            note = QLabel("No preferences available for this platform.")
            note.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            layout.addWidget(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(btns)

    def _build_colima_group(self) -> QGroupBox:
        from src.workers.colima_worker import (
            DEFAULT_CPU, DEFAULT_MEMORY, DEFAULT_DISK,
            get_preferred_resources, colima_installed, colima_running,
        )

        group = QGroupBox("Colima resources")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(12, 16, 12, 12)

        cpu, memory, disk = get_preferred_resources()

        self._cpu = QSpinBox()
        self._cpu.setRange(1, 64)
        self._cpu.setValue(cpu)
        self._cpu.setSuffix(" cores")
        self._cpu.setStyleSheet(_spin_style())
        self._cpu.setToolTip(f"CPUs for the Colima VM (Colima default: {DEFAULT_CPU})")
        form.addRow("CPU:", self._cpu)

        self._memory = QSpinBox()
        self._memory.setRange(1, 128)
        self._memory.setValue(memory)
        self._memory.setSuffix(" GiB")
        self._memory.setStyleSheet(_spin_style())
        self._memory.setToolTip(f"Memory for the Colima VM (Colima default: {DEFAULT_MEMORY} GiB)")
        form.addRow("Memory:", self._memory)

        self._disk = QSpinBox()
        self._disk.setRange(1, 2000)
        self._disk.setValue(disk)
        self._disk.setSuffix(" GiB")
        self._disk.setStyleSheet(_spin_style())
        self._disk.setToolTip(
            f"Disk for container data (Colima default: {DEFAULT_DISK} GiB).\n"
            "After the VM exists, disk size can only be increased."
        )
        form.addRow("Disk:", self._disk)

        hint_bits = [
            f"Showing current values (Colima defaults are "
            f"{DEFAULT_CPU} CPU / {DEFAULT_MEMORY} GiB / {DEFAULT_DISK} GiB disk).",
            "Saved values are used the next time Colima starts.",
        ]
        if not colima_installed():
            hint_bits.append("Colima is not installed yet.")
        elif colima_running():
            hint_bits.append(
                "Colima is running — stop and start Docker again for changes to apply."
            )

        hint = QLabel(" ".join(hint_bits))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; font-weight: normal;")
        form.addRow(hint)

        return group

    def _build_linux_group(self) -> QGroupBox:
        group = QGroupBox("Appearance")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        form.setContentsMargins(12, 16, 12, 12)

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
        return group

    def _apply(self):
        if _MACOS and self._cpu is not None:
            from src.workers.colima_worker import save_preferred_resources
            save_preferred_resources(
                self._cpu.value(),
                self._memory.value(),
                self._disk.value(),
            )

        if _LINUX and self._icon_theme is not None:
            chosen = self._icon_theme.currentText()
            theme_name = "" if chosen == _SYSTEM_DEFAULT else chosen
            self._settings.setValue("icon_theme", theme_name)
            if theme_name:
                QIcon.setThemeName(theme_name)

            parent = self.parent()
            if parent is not None and hasattr(parent, "refresh_icons"):
                parent.refresh_icons()

    def _save(self):
        self._apply()
        self.accept()
