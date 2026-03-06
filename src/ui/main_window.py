from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame,
    QSizePolicy, QStatusBar, QMessageBox, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QProcess
from PyQt6.QtGui import QFont, QColor
import shutil
import sys

from src.docker_client import DockerClient


# ── Docker daemon starter ────────────────────────────────────────────────────

def _detect_docker_launcher() -> tuple[str, list[str]] | None:
    """
    Return (label, command_list) for the first available daemon launcher,
    or None if nothing is found.

    Priority: Colima → OrbStack → Rancher Desktop → Docker Desktop → Linux systemd
    """
    if sys.platform == "darwin":
        if shutil.which("colima"):
            return ("Colima", ["colima", "start"])
        orb = "/Applications/OrbStack.app/Contents/MacOS/OrbStack"
        if shutil.which("orb") or __import__("os").path.exists(orb):
            return ("OrbStack", ["open", "-a", "OrbStack"])
        rancher = "/Applications/Rancher Desktop.app"
        if __import__("os").path.exists(rancher):
            return ("Rancher Desktop", ["open", "-a", "Rancher Desktop"])
        docker_app = "/Applications/Docker.app"
        if __import__("os").path.exists(docker_app):
            return ("Docker Desktop", ["open", "-a", "Docker"])
        return None
    else:
        # Linux
        if shutil.which("systemctl"):
            return ("Docker (systemd)", ["sudo", "systemctl", "start", "docker"])
        if shutil.which("service"):
            return ("Docker (service)", ["sudo", "service", "docker", "start"])
        return None


# ── Colours ────────────────────────────────────────────────────────────────
BG       = "#1e1e1e"
SIDEBAR  = "#252526"
ACCENT   = "#0078d4"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
BORDER   = "#3e3e42"
SUCCESS  = "#16c60c"
ERROR    = "#f85149"


class NavButton(QPushButton):
    """Sidebar navigation item."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self._icon_text = icon
        self._label_text = label
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        icon_lbl = QLabel(self._icon_text)
        # Use platform-appropriate emoji font to avoid Qt font-fallback delay
        import sys
        emoji_font = "Apple Color Emoji" if sys.platform == "darwin" else "Segoe UI Emoji"
        icon_lbl.setFont(QFont(emoji_font, 16))
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_lbl)

        text_lbl = QLabel(self._label_text)
        f = QFont("SF Pro Display, Helvetica Neue, Arial", 13)
        text_lbl.setFont(f)
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(text_lbl)
        layout.addStretch()

        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._update_style(checked)

    def _update_style(self, active: bool):
        bg   = ACCENT if active else "transparent"
        fg   = "#ffffff" if active else TEXT
        hover = "#2a2d2e" if not active else ACCENT
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                border: none;
                border-radius: 6px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """)


class Sidebar(QFrame):
    nav_changed = pyqtSignal(int)

    ITEMS = [
        ("🐳", "Containers",  0),
        ("📦", "Compose",     1),
        ("💿", "Images",      2),
        ("💾", "Volumes",     3),
        ("🌐", "Networks",    4),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"background: {SIDEBAR}; border-right: 1px solid {BORDER};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        # Logo
        logo = QLabel("DockPilot")
        logo.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold; padding: 8px 12px;")
        layout.addWidget(logo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)
        layout.addSpacing(6)

        self._buttons: list[NavButton] = []
        for icon, label, idx in self.ITEMS:
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda _, i=idx: self._select(i))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

        # "Start Docker" button — shown only when daemon is not running
        self._start_docker_btn = QPushButton("Start Docker")
        self._start_docker_btn.setFixedHeight(30)
        self._start_docker_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_docker_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SUCCESS};
                color: #000000;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
                margin: 0 4px;
            }}
            QPushButton:hover {{ background: #12a50a; }}
            QPushButton:disabled {{ background: #444444; color: #777777; }}
        """)
        self._start_docker_btn.setVisible(False)
        self._start_docker_btn.clicked.connect(self._on_start_docker)
        layout.addWidget(self._start_docker_btn)

        # Docker status indicator
        self._status_dot = QLabel("●")
        self._status_label = QLabel("Connecting…")
        self._status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self._status_dot.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")

        status_row = QHBoxLayout()
        status_row.setContentsMargins(12, 0, 0, 0)
        status_row.setSpacing(6)
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        self._select(0)

    def _on_start_docker(self):
        launcher = _detect_docker_launcher()
        if not launcher:
            return
        label, cmd = launcher
        self._start_docker_btn.setEnabled(False)
        self._start_docker_btn.setText(f"Starting {label}…")
        proc = QProcess()
        proc.startDetached(cmd[0], cmd[1:])
        # Re-enable after 3 s; the status poller will detect when daemon is up
        QTimer.singleShot(3000, lambda: (
            self._start_docker_btn.setEnabled(True),
            self._start_docker_btn.setText("Start Docker"),
        ))

    def _select(self, index: int):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self.nav_changed.emit(index)

    def set_docker_status(self, connected: bool, version: str = ""):
        if connected:
            self._status_dot.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
            self._status_label.setText(version or "Connected")
            self._start_docker_btn.setVisible(False)
        else:
            self._status_dot.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
            self._status_label.setText("Not connected")
            # Show "Start Docker" only if we know how to start something
            has_launcher = _detect_docker_launcher() is not None
            self._start_docker_btn.setVisible(has_launcher)
            if has_launcher:
                label = _detect_docker_launcher()[0]
                self._start_docker_btn.setText(f"Start {label}")


# ── Main Window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, docker: DockerClient):
        super().__init__()
        self._docker = docker
        self.setWindowTitle("DockPilot")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(f"QMainWindow {{ background: {BG}; }}")

        self._build_ui()
        self._start_status_poll()

    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.nav_changed.connect(self._on_nav)
        root.addWidget(self._sidebar)

        # Content stack — panels are lazy-loaded
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {BG};")
        root.addWidget(self._stack, 1)

        # Placeholder panels inserted in order matching sidebar ITEMS
        self._panels: list[QWidget | None] = [None] * 5
        for _ in range(5):
            placeholder = QWidget()
            self._stack.addWidget(placeholder)

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet(f"background: {SIDEBAR}; color: {TEXT_DIM}; font-size: 11px; border-top: 1px solid {BORDER};")
        self.setStatusBar(sb)
        self._status_bar = sb

        # Load initial panel (Containers) — the Sidebar emitted nav_changed(0)
        # before our signal was connected, so we trigger it manually here.
        self._ensure_panel(0)

    def _on_nav(self, index: int):
        self._ensure_panel(index)
        self._stack.setCurrentIndex(index)

    def _ensure_panel(self, index: int):
        if self._panels[index] is not None:
            return
        panel = self._create_panel(index)
        self._panels[index] = panel
        self._stack.removeWidget(self._stack.widget(index))
        self._stack.insertWidget(index, panel)
        self._stack.setCurrentIndex(index)

    def _create_panel(self, index: int) -> QWidget:
        from src.ui.containers_panel import ContainersPanel
        from src.ui.compose_panel   import ComposePanel
        from src.ui.images_panel    import ImagesPanel
        from src.ui.volumes_panel   import VolumesPanel
        from src.ui.networks_panel  import NetworksPanel

        panels = [ContainersPanel, ComposePanel, ImagesPanel, VolumesPanel, NetworksPanel]
        cls = panels[index]
        panel = cls(self._docker, self)
        return panel

    # ------------------------------------------------------------------
    # Docker status polling
    # ------------------------------------------------------------------

    def _start_status_poll(self):
        self._check_docker_status()
        timer = QTimer(self)
        timer.timeout.connect(self._check_docker_status)
        timer.start(5000)

    def _check_docker_status(self):
        ok = self._docker.ping()
        version = ""
        if ok:
            v = self._docker.version()
            if v:
                engine = v.get("Components", [{}])[0].get("Version", "")
                version = f"Docker {engine}" if engine else "Docker"
        self._sidebar.set_docker_status(ok, version)
        if ok:
            self._status_bar.showMessage("Docker daemon connected", 3000)
        else:
            self._status_bar.showMessage("Docker daemon not reachable — start Docker Desktop or daemon")

    def show_status(self, msg: str, timeout: int = 4000):
        self._status_bar.showMessage(msg, timeout)
