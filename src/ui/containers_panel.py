from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView,
    QFrame, QToolButton, QMenu, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon

from src.docker_client import DockerClient
from src.workers.action_worker import ActionWorker, FetchWorker

# ── Palette ─────────────────────────────────────────────────────────────────
BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"
YELLOW   = "#ffb900"
BLUE     = "#4ec9b0"

STATUS_COLORS = {
    "running":  GREEN,
    "paused":   YELLOW,
    "exited":   RED,
    "created":  TEXT_DIM,
    "dead":     RED,
    "restarting": YELLOW,
}

COLS = ["", "ID", "Name", "Ports", "Status", "Image"]
COL_DOT    = 0
COL_ID     = 1
COL_NAME   = 2
COL_PORTS  = 3
COL_STATUS = 4
COL_IMAGE  = 5


def _fmt_ports(ports: dict) -> str:
    if not ports:
        return ""
    parts = []
    for container_port, host_bindings in ports.items():
        if host_bindings:
            for b in host_bindings:
                host_ip   = b.get("HostIp", "0.0.0.0")
                host_port = b.get("HostPort", "?")
                parts.append(f"{host_ip}:{host_port}->{container_port}")
        else:
            parts.append(container_port)
    return "  ".join(parts[:3]) + ("…" if len(parts) > 3 else "")


def _fmt_image(name: str) -> str:
    if ":" in name:
        repo, tag = name.rsplit(":", 1)
        if "/" in repo:
            repo = repo.split("/")[-1]
        return f"{repo}:{tag}"
    return name.split("/")[-1] if "/" in name else name


def _short_id(full_id: str) -> str:
    return full_id[:12]


def _hex6(color: str) -> str:
    """Expand #rgb shorthand to #rrggbb so CSS alpha suffixes are valid."""
    if color.startswith("#") and len(color) == 4:
        r, g, b = color[1], color[2], color[3]
        return f"#{r}{r}{g}{g}{b}{b}"
    return color


class ActionButton(QPushButton):
    def __init__(self, text: str, color: str = ACCENT, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(26)
        self.setFixedWidth(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        c = _hex6(color)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {c};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 0 8px;
            }}
            QPushButton:hover {{ background: {c}cc; }}
            QPushButton:disabled {{ background: #444444; color: #777777; }}
        """)


class ContainersPanel(QWidget):
    def __init__(self, docker: DockerClient, main_window=None):
        super().__init__()
        self._docker = docker
        self._main_window = main_window
        self._containers: list = []
        self._workers: list[ActionWorker] = []
        self._refresh_timer = QTimer(self)
        self._build_ui()
        self._start_auto_refresh()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        tb_layout.setSpacing(8)

        title = QLabel("Containers")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        tb_layout.addWidget(title)

        tb_layout.addStretch()

        # Show all toggle
        self._all_check = QCheckBox("Show all")
        self._all_check.setChecked(True)
        self._all_check.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        self._all_check.toggled.connect(self._refresh)
        tb_layout.addWidget(self._all_check)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter containers…")
        self._search.setFixedWidth(220)
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
        self._search.textChanged.connect(self._apply_filter)
        tb_layout.addWidget(self._search)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        tb_layout.addWidget(refresh_btn)

        # Prune button
        prune_btn = QPushButton("Prune stopped")
        prune_btn.setFixedHeight(32)
        prune_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prune_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG};
                color: {YELLOW};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2a2d2e; }}
        """)
        prune_btn.clicked.connect(self._prune_containers)
        tb_layout.addWidget(prune_btn)

        layout.addWidget(toolbar)

        # Auto-refresh indicator
        self._refresh_label = QLabel("")
        self._refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._refresh_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; padding-right: 8px;")
        layout.addWidget(self._refresh_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(COLS))
        self._table.setHorizontalHeaderLabels(COLS)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG};
                color: {TEXT};
                gridline-color: {BORDER};
                border: none;
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background: {ACCENT}44;
            }}
            QHeaderView::section {{
                background: {SURFACE};
                color: {TEXT_DIM};
                border: none;
                border-bottom: 1px solid {BORDER};
                padding: 6px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.doubleClicked.connect(self._on_double_click)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_DOT,    QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ID,     QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NAME,   QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_PORTS,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_IMAGE,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_DOT,     24)
        self._table.setColumnWidth(COL_ID,     100)
        self._table.setColumnWidth(COL_NAME,   160)
        self._table.setColumnWidth(COL_STATUS,  90)
        self._table.setColumnWidth(COL_IMAGE,  160)

        layout.addWidget(self._table, 1)

        # Action bar at bottom
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        action_bar.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(16, 8, 16, 8)
        ab_layout.setSpacing(8)

        self._btn_start   = ActionButton("Start",   "#1e7e34")
        self._btn_stop    = ActionButton("Stop",    "#c0392b")
        self._btn_restart = ActionButton("Restart", "#856404")
        self._btn_logs    = ActionButton("Logs",    "#555")
        self._btn_terminal= ActionButton("Terminal","#555")
        self._btn_inspect = ActionButton("Inspect", "#555")
        self._btn_remove  = ActionButton("Remove",  RED)

        for btn in [self._btn_start, self._btn_stop, self._btn_restart,
                    self._btn_logs, self._btn_terminal, self._btn_inspect,
                    self._btn_remove]:
            btn.setEnabled(False)
            ab_layout.addWidget(btn)

        ab_layout.addStretch()
        self._selected_label = QLabel("No container selected")
        self._selected_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        ab_layout.addWidget(self._selected_label)

        self._btn_start.clicked.connect(lambda: self._action("start"))
        self._btn_stop.clicked.connect(lambda: self._action("stop"))
        self._btn_restart.clicked.connect(lambda: self._action("restart"))
        self._btn_logs.clicked.connect(self._open_logs)
        self._btn_terminal.clicked.connect(self._open_terminal)
        self._btn_inspect.clicked.connect(self._open_inspect)
        self._btn_remove.clicked.connect(self._remove_container)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(action_bar)

    # ── Data ────────────────────────────────────────────────────────────

    def _start_auto_refresh(self):
        self._refresh()
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(5000)

    def _refresh(self):
        if getattr(self, "_fetch_worker", None) and self._fetch_worker.isRunning():
            return
        show_all = self._all_check.isChecked()

        def fetch():
            if not self._docker.is_connected:
                self._docker.ping()
            return self._docker.containers(all=show_all), self._docker.is_connected

        self._fetch_worker = FetchWorker(fetch, self)
        self._fetch_worker.result.connect(self._on_fetched)
        self._fetch_worker.start()

    def _on_fetched(self, data):
        containers, connected = data
        self._containers = containers
        self._populate_table()
        if connected:
            self._refresh_label.setText("Auto-refresh: 5 s")
        else:
            self._refresh_label.setText("Docker not running — waiting…")

    def _populate_table(self):
        flt = self._search.text().lower()
        rows = []
        for c in self._containers:
            name = c.name or ""
            image = c.image.tags[0] if c.image.tags else c.image.short_id
            if flt and flt not in name.lower() and flt not in image.lower():
                continue
            rows.append(c)

        self._table.setRowCount(len(rows))
        for row, c in enumerate(rows):
            status = c.status
            color  = STATUS_COLORS.get(status, TEXT_DIM)

            name  = c.name or ""
            image = c.image.tags[0] if c.image.tags else c.image.short_id
            ports = _fmt_ports(c.ports)
            cid   = _short_id(c.id)

            # Status dot
            dot = QTableWidgetItem("●")
            dot.setForeground(QColor(color))
            dot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setData(Qt.ItemDataRole.UserRole, c.id)
            self._table.setItem(row, COL_DOT, dot)

            def cell(text: str) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setForeground(QColor(TEXT))
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                return item

            status_item = cell(status)
            status_item.setForeground(QColor(color))

            self._table.setItem(row, COL_ID,     cell(cid))
            self._table.setItem(row, COL_NAME,   cell(name))
            self._table.setItem(row, COL_PORTS,  cell(ports))
            self._table.setItem(row, COL_STATUS, status_item)
            self._table.setItem(row, COL_IMAGE,  cell(_fmt_image(image)))

            self._table.setRowHeight(row, 34)

    def _apply_filter(self):
        self._populate_table()

    # ── Selection ────────────────────────────────────────────────────────

    def _selected_container_id(self) -> str | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), COL_DOT)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection_changed(self):
        cid = self._selected_container_id()
        has = cid is not None
        for btn in [self._btn_start, self._btn_stop, self._btn_restart,
                    self._btn_logs, self._btn_terminal, self._btn_inspect,
                    self._btn_remove]:
            btn.setEnabled(has)
        if has:
            c = self._docker.get_container(cid)
            if c:
                self._selected_label.setText(f"{c.name}  [{c.status}]")
        else:
            self._selected_label.setText("No container selected")

    def _on_double_click(self, index):
        self._open_logs()

    # ── Actions ──────────────────────────────────────────────────────────

    def _action(self, op: str):
        cid = self._selected_container_id()
        if not cid:
            return
        fn_map = {
            "start":   self._docker.start_container,
            "stop":    self._docker.stop_container,
            "restart": self._docker.restart_container,
        }
        fn = fn_map.get(op)
        if not fn:
            return
        w = ActionWorker(fn, cid)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(lambda e: self._show_error(e))
        self._workers.append(w)
        w.start()

    def _remove_container(self):
        cid = self._selected_container_id()
        if not cid:
            return
        c = self._docker.get_container(cid)
        name = c.name if c else cid[:12]
        reply = QMessageBox.question(
            self, "Remove container",
            f"Remove container '{name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.remove_container, cid, force=True)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _prune_containers(self):
        reply = QMessageBox.question(
            self, "Prune stopped containers",
            "Remove all stopped containers?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.raw.containers.prune)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _open_logs(self):
        cid = self._selected_container_id()
        if not cid:
            return
        from src.ui.logs_dialog import LogsDialog
        dlg = LogsDialog(self._docker, cid, self)
        dlg.show()

    def _open_terminal(self):
        cid = self._selected_container_id()
        if not cid:
            return
        from src.ui.terminal_widget import ContainerTerminalDialog
        dlg = ContainerTerminalDialog(cid, self)
        dlg.show()

    def _open_inspect(self):
        cid = self._selected_container_id()
        if not cid:
            return
        from src.ui.inspect_dialog import InspectDialog
        try:
            data = self._docker.inspect_container(cid)
        except Exception as e:
            self._show_error(str(e))
            return
        dlg = InspectDialog("Container inspect", data, self)
        dlg.show()

    def _open_stats(self):
        cid = self._selected_container_id()
        if not cid:
            return
        from src.ui.stats_widget import StatsDialog
        dlg = StatsDialog(self._docker, cid, self)
        dlg.show()

    # ── Context menu ────────────────────────────────────────────────────

    def _context_menu(self, pos):
        cid = self._selected_container_id()
        if not cid:
            return
        c = self._docker.get_container(cid)
        if not c:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: #2d2d2d; color: {TEXT}; border: 1px solid {BORDER}; }}
            QMenu::item:selected {{ background: {ACCENT}; }}
        """)

        if c.status == "running":
            menu.addAction("Stop",   lambda: self._action("stop"))
            menu.addAction("Restart",lambda: self._action("restart"))
            menu.addAction("Pause",  lambda: self._do_pause(cid))
        elif c.status == "paused":
            menu.addAction("Unpause",lambda: self._do_unpause(cid))
        else:
            menu.addAction("Start",  lambda: self._action("start"))

        menu.addSeparator()
        menu.addAction("Logs",    self._open_logs)
        menu.addAction("Terminal",self._open_terminal)
        menu.addAction("Stats",   self._open_stats)
        menu.addAction("Inspect", self._open_inspect)
        menu.addSeparator()
        menu.addAction("Remove (force)", self._remove_container)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _do_pause(self, cid: str):
        w = ActionWorker(self._docker.pause_container, cid)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _do_unpause(self, cid: str):
        w = ActionWorker(self._docker.unpause_container, cid)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
