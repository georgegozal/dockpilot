"""Menu-bar / system-tray icon: quick Show / Preferences / Open at Login / Quit."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from src import login_item


def _build_icon() -> QIcon:
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font_name = "Apple Color Emoji" if sys.platform == "darwin" else "Noto Color Emoji"
    painter.setFont(QFont(font_name, int(size * 0.8)))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\U0001F433")  # 🐳
    painter.end()
    return QIcon(pixmap)


def setup_tray(app, window) -> QSystemTrayIcon | None:
    """Create the menu-bar/tray icon. Returns None if no tray is available."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    tray = QSystemTrayIcon(_build_icon(), app)
    tray.setToolTip("DockPilot")

    menu = QMenu()

    show_action = QAction("Show DockPilot", menu)
    show_action.triggered.connect(lambda: _show_window(window))
    menu.addAction(show_action)

    menu.addSeparator()

    prefs_action = QAction("Preferences…", menu)
    prefs_action.triggered.connect(lambda: _open_preferences(window))
    menu.addAction(prefs_action)

    login_action = QAction("Open at Login", menu)
    login_action.setCheckable(True)
    login_action.setEnabled(login_item.is_supported())
    login_action.setChecked(login_item.is_enabled())
    login_action.toggled.connect(login_item.set_enabled)
    menu.addAction(login_action)

    menu.addSeparator()

    quit_action = QAction("Quit DockPilot", menu)
    quit_action.triggered.connect(lambda: _quit(window))
    menu.addAction(quit_action)

    # Re-sync the checkmark each time the menu opens in case the LaunchAgent /
    # autostart entry was removed by hand outside of DockPilot.
    menu.aboutToShow.connect(lambda: login_action.setChecked(login_item.is_enabled()))

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: _show_window(window)
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    return tray


def _show_window(window):
    window.show()
    window.raise_()
    window.activateWindow()


def _open_preferences(window):
    from src.ui.preferences_dialog import PreferencesDialog
    dlg = PreferencesDialog(window)
    dlg.exec()


def _quit(window):
    window._quit_requested = True
    if not window.isVisible():
        window.show()
    window.close()
