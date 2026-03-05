from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

from src.docker_client import DockerClient
from src.ui.main_window import MainWindow


DARK_PALETTE = {
    "Window":           "#1e1e1e",
    "WindowText":       "#cccccc",
    "Base":             "#252526",
    "AlternateBase":    "#2d2d2d",
    "ToolTipBase":      "#3c3c3c",
    "ToolTipText":      "#cccccc",
    "Text":             "#cccccc",
    "Button":           "#2d2d2d",
    "ButtonText":       "#cccccc",
    "BrightText":       "#ffffff",
    "Highlight":        "#0078d4",
    "HighlightedText":  "#ffffff",
    "Link":             "#4ec9b0",
    "Mid":              "#3e3e42",
    "Dark":             "#1a1a1a",
    "Shadow":           "#111111",
    "Light":            "#3e3e42",
}


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    for role_name, color in DARK_PALETTE.items():
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is not None:
            pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet("""
        QToolTip {
            color: #cccccc;
            background-color: #3c3c3c;
            border: 1px solid #555;
        }
        QScrollBar:vertical {
            background: #252526;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #555;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover { background: #777; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal {
            background: #252526;
            height: 10px;
        }
        QScrollBar::handle:horizontal {
            background: #555;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover { background: #777; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    """)


class DockPilotApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("DockPilot")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("DockPilot")

        apply_dark_palette(self)

        self.docker = DockerClient()
        self.window = MainWindow(self.docker)
        self.window.show()
