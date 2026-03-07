from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame,
    QStatusBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
import sys

from src.docker_client import DockerClient
from src.workers.action_worker import FetchWorker
from src.workers.colima_worker import (
    colima_installed, colima_running,
    ColimaStartWorker, ColimaStopWorker,
)


# ── Colours ────────────────────────────────────────────────────────────────
BG       = "#1e1e1e"
SIDEBAR  = "#252526"
ACCENT   = "#0078d4"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
BORDER   = "#3e3e42"
SUCCESS  = "#16c60c"
ERROR    = "#f85149"
YELLOW   = "#ffb900"


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

        import sys
        emoji_font = "Apple Color Emoji" if sys.platform == "darwin" else "Segoe UI Emoji"

        self._icon_lbl = QLabel(self._icon_text)
        self._icon_lbl.setFont(QFont(emoji_font, 16))
        self._icon_lbl.setFixedWidth(24)
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(self._label_text)
        self._text_lbl.setFont(QFont("Helvetica Neue", 13))
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._text_lbl)
        layout.addStretch()

        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._update_style(checked)

    def _update_style(self, active: bool):
        fg = "#ffffff" if active else TEXT
        bg = "#094771" if active else "transparent"
        hover = "#0e5a8a" if active else "#2a2d2e"
        # Child labels must be transparent so the button background shows through
        lbl_style = f"background: transparent; color: {fg}; border: none;"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: none;
                border-radius: 4px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """)
        if hasattr(self, "_icon_lbl"):
            self._icon_lbl.setStyleSheet(lbl_style)
            self._text_lbl.setStyleSheet(lbl_style)


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

    def _select(self, index: int):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self.nav_changed.emit(index)

    def set_docker_status(self, connected: bool, version: str = "", starting: bool = False):
        if starting:
            self._status_dot.setStyleSheet(f"color: {YELLOW}; font-size: 10px;")
            self._status_label.setText("Starting Docker…")
        elif connected:
            self._status_dot.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
            self._status_label.setText(version or "Connected")
        else:
            self._status_dot.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
            self._status_label.setText("Not connected")


# ── Main Window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, docker: DockerClient):
        super().__init__()
        self._docker = docker
        self.setWindowTitle("DockPilot")
        self.resize(900, 600)
        self.setMinimumSize(480, 300)
        self.setStyleSheet(f"QMainWindow {{ background: {BG}; }}")

        self._colima_started_by_us = False
        self._colima_stop_done = False
        self._colima_worker: ColimaStartWorker | ColimaStopWorker | None = None

        self._build_ui()
        self._start_status_poll()
        self._maybe_start_colima()

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
        # Skip if a status fetch is already in flight
        if getattr(self, "_status_worker", None) and self._status_worker.isRunning():
            return
        starting = isinstance(self._colima_worker, ColimaStartWorker)

        def fetch():
            ok = self._docker.ping()
            version = ""
            if ok:
                v = self._docker.version()
                if v:
                    engine = v.get("Components", [{}])[0].get("Version", "")
                    version = f"Docker {engine}" if engine else "Docker"
            return ok, version

        self._status_worker = FetchWorker(fetch, self)
        self._status_worker.result.connect(
            lambda r: self._on_status_result(r[0], r[1], starting)
        )
        self._status_worker.start()

    def _on_status_result(self, ok: bool, version: str, starting: bool):
        self._sidebar.set_docker_status(ok, version, starting=starting)
        if ok:
            self._status_bar.showMessage("Docker daemon connected", 3000)
        elif not starting:
            self._status_bar.showMessage("Docker daemon not reachable")

    # ------------------------------------------------------------------
    # Colima lifecycle
    # ------------------------------------------------------------------

    def _maybe_start_colima(self):
        """Auto-start Colima if it is installed but not yet running (macOS only)."""
        if sys.platform != "darwin":
            return
        if not colima_installed():
            return
        if colima_running():
            return  # already up — don't touch it, don't stop it on exit

        self._status_bar.showMessage("Starting Colima VM…")
        w = ColimaStartWorker(self)
        w.success.connect(self._on_colima_started)
        w.error.connect(self._on_colima_error)
        w.finished.connect(lambda: setattr(self, "_colima_worker", None))
        self._colima_worker = w
        w.start()

    def _on_colima_started(self):
        self._colima_started_by_us = True
        self._status_bar.showMessage("Colima started", 3000)

    def _on_colima_error(self, msg: str):
        self._status_bar.showMessage(f"Colima error: {msg}", 8000)

    def _stop_colima_and_close(self):
        self._status_bar.showMessage("Stopping Colima VM…")
        w = ColimaStopWorker(self)
        w.finished.connect(self._on_colima_stop_done)
        w.finished.connect(lambda: setattr(self, "_colima_worker", None))
        self._colima_worker = w
        w.start()

    def _on_colima_stop_done(self):
        self._colima_stop_done = True
        self.close()

    def closeEvent(self, event):
        if sys.platform == "darwin" and not self._colima_stop_done and colima_installed() and colima_running():
            msg = QMessageBox(self)
            msg.setWindowTitle("Quit DockPilot")
            msg.setText("Docker (Colima) is running.")
            msg.setInformativeText(
                "Stop Docker when quitting, or keep it running in the background?"
            )
            stop_btn   = msg.addButton("Stop Docker",  QMessageBox.ButtonRole.DestructiveRole)
            keep_btn   = msg.addButton("Keep Running", QMessageBox.ButtonRole.AcceptRole)
            cancel_btn = msg.addButton("Cancel",       QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(keep_btn)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == cancel_btn:
                event.ignore()
                return
            elif clicked == stop_btn:
                event.ignore()
                self._stop_colima_and_close()
                return
            # keep_btn → close without stopping Colima
        super().closeEvent(event)

    # ------------------------------------------------------------------

    def show_status(self, msg: str, timeout: int = 4000):
        self._status_bar.showMessage(msg, timeout)
