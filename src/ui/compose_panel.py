from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFrame, QLineEdit, QMessageBox, QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from src.docker_client import DockerClient
from src.workers.action_worker import ActionWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"
YELLOW   = "#ffb900"

STATUS_COLORS = {
    "running":   GREEN,
    "paused":    YELLOW,
    "exited":    RED,
    "created":   TEXT_DIM,
    "dead":      RED,
    "restarting":YELLOW,
}

LABEL_PROJECT = "com.docker.compose.project"
LABEL_SERVICE = "com.docker.compose.service"


class ComposePanel(QWidget):
    def __init__(self, docker: DockerClient, main_window=None):
        super().__init__()
        self._docker = docker
        self._main_window = main_window
        self._workers: list[ActionWorker] = []
        self._build_ui()
        self._start_auto_refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 8, 16, 8)
        tb.setSpacing(8)

        title = QLabel("Compose Groups")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        tb.addWidget(title)
        tb.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter projects…")
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
        self._search.textChanged.connect(self._apply_filter)
        tb.addWidget(self._search)

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
        tb.addWidget(refresh_btn)
        layout.addWidget(toolbar)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Service / Project", "Status", "Image", "Ports"])
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {BG};
                color: {TEXT};
                border: none;
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 4px 0;
                border-bottom: 1px solid {BORDER};
            }}
            QTreeWidget::item:selected {{ background: {ACCENT}44; }}
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
        self._tree.setAlternatingRowColors(False)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.setColumnWidth(0, 240)
        self._tree.setColumnWidth(1, 90)
        self._tree.setColumnWidth(2, 180)

        self._tree.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._tree, 1)

        # Action bar
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        action_bar.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        ab = QHBoxLayout(action_bar)
        ab.setContentsMargins(16, 8, 16, 8)
        ab.setSpacing(8)

        def _btn(label, color=ACCENT):
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setFixedWidth(110)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {color}cc; }}
                QPushButton:disabled {{ background: #444; color: #777; }}
            """)
            return b

        self._btn_start_all  = _btn("Start all",   "#1e7e34")
        self._btn_stop_all   = _btn("Stop all",    "#c0392b")
        self._btn_restart_all= _btn("Restart all", "#856404")
        self._btn_logs       = _btn("Logs",        "#555")
        self._btn_terminal   = _btn("Terminal",    "#555")

        for btn in [self._btn_start_all, self._btn_stop_all,
                    self._btn_restart_all, self._btn_logs, self._btn_terminal]:
            btn.setEnabled(False)
            ab.addWidget(btn)

        self._btn_start_all.clicked.connect(lambda: self._group_action("start"))
        self._btn_stop_all.clicked.connect(lambda: self._group_action("stop"))
        self._btn_restart_all.clicked.connect(lambda: self._group_action("restart"))
        self._btn_logs.clicked.connect(self._open_logs)
        self._btn_terminal.clicked.connect(self._open_terminal)

        ab.addStretch()
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        ab.addWidget(self._info_label)
        layout.addWidget(action_bar)

    # ── Data ────────────────────────────────────────────────────────────

    def _start_auto_refresh(self):
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(5000)

    def _refresh(self):
        containers = self._docker.containers(all=True)
        # Group by compose project label
        projects: dict[str, list] = {}
        standalone: list = []
        for c in containers:
            project = c.labels.get(LABEL_PROJECT)
            if project:
                projects.setdefault(project, []).append(c)
            else:
                standalone.append(c)

        self._projects = projects
        self._standalone = standalone
        self._populate_tree(projects, standalone)

    def _populate_tree(self, projects: dict, standalone: list):
        flt = self._search.text().lower()
        self._tree.clear()

        font_bold = QFont()
        font_bold.setBold(True)

        for proj_name, containers in sorted(projects.items()):
            if flt and flt not in proj_name.lower():
                # Check if any service matches
                if not any(flt in c.name.lower() for c in containers):
                    continue

            # Count running
            running = sum(1 for c in containers if c.status == "running")
            total   = len(containers)
            status_text = f"{running}/{total} running"
            status_color = GREEN if running == total else (YELLOW if running > 0 else RED)

            proj_item = QTreeWidgetItem(self._tree)
            proj_item.setText(0, f"  {proj_name}")
            proj_item.setText(1, status_text)
            proj_item.setFont(0, font_bold)
            proj_item.setForeground(0, QColor(TEXT))
            proj_item.setForeground(1, QColor(status_color))
            proj_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "name": proj_name})
            proj_item.setExpanded(True)

            for c in sorted(containers, key=lambda x: x.name):
                service = c.labels.get(LABEL_SERVICE, c.name)
                image   = c.image.tags[0] if c.image.tags else c.image.short_id
                ports   = self._fmt_ports(c.ports)
                color   = STATUS_COLORS.get(c.status, TEXT_DIM)

                svc_item = QTreeWidgetItem(proj_item)
                svc_item.setText(0, f"    {service}")
                svc_item.setText(1, c.status)
                svc_item.setText(2, self._fmt_image(image))
                svc_item.setText(3, ports)
                svc_item.setForeground(1, QColor(color))
                svc_item.setForeground(0, QColor(TEXT))
                svc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "container", "id": c.id})

        # Standalone containers (not in any compose project)
        if standalone:
            if not flt or any(flt in c.name.lower() for c in standalone):
                standalone_item = QTreeWidgetItem(self._tree)
                standalone_item.setText(0, "  Standalone containers")
                standalone_item.setFont(0, font_bold)
                standalone_item.setForeground(0, QColor(TEXT_DIM))
                standalone_item.setExpanded(True)

                for c in sorted(standalone, key=lambda x: x.name):
                    if flt and flt not in c.name.lower():
                        continue
                    image = c.image.tags[0] if c.image.tags else c.image.short_id
                    ports = self._fmt_ports(c.ports)
                    color = STATUS_COLORS.get(c.status, TEXT_DIM)

                    ci = QTreeWidgetItem(standalone_item)
                    ci.setText(0, f"    {c.name}")
                    ci.setText(1, c.status)
                    ci.setText(2, self._fmt_image(image))
                    ci.setText(3, ports)
                    ci.setForeground(1, QColor(color))
                    ci.setForeground(0, QColor(TEXT))
                    ci.setData(0, Qt.ItemDataRole.UserRole, {"type": "container", "id": c.id})

    def _apply_filter(self):
        self._populate_tree(getattr(self, "_projects", {}), getattr(self, "_standalone", []))

    @staticmethod
    def _fmt_ports(ports: dict) -> str:
        if not ports:
            return ""
        parts = []
        for cp, hbs in ports.items():
            if hbs:
                for b in hbs:
                    parts.append(f"{b.get('HostPort','?')}->{cp}")
            else:
                parts.append(cp)
        return "  ".join(parts[:3]) + ("…" if len(parts) > 3 else "")

    @staticmethod
    def _fmt_image(name: str) -> str:
        if ":" in name:
            repo, tag = name.rsplit(":", 1)
            repo = repo.split("/")[-1]
            return f"{repo}:{tag}"
        return name.split("/")[-1] if "/" in name else name

    # ── Selection ────────────────────────────────────────────────────────

    def _on_selection(self):
        item = self._tree.currentItem()
        if not item:
            for b in [self._btn_start_all, self._btn_stop_all,
                      self._btn_restart_all, self._btn_logs, self._btn_terminal]:
                b.setEnabled(False)
            self._info_label.setText("")
            return

        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        kind = data.get("type")
        for b in [self._btn_start_all, self._btn_stop_all,
                  self._btn_restart_all, self._btn_logs, self._btn_terminal]:
            b.setEnabled(True)
        if kind == "project":
            name = data.get("name", "")
            containers = self._projects.get(name, [])
            self._info_label.setText(f"Project '{name}': {len(containers)} service(s)")
        elif kind == "container":
            cid = data.get("id", "")
            c = self._docker.get_container(cid)
            if c:
                self._info_label.setText(f"{c.name}  [{c.status}]")
        else:
            self._info_label.setText("")

    def _get_selected_ids(self) -> list[str]:
        """Return container IDs for the selected item (project or single)."""
        item = self._tree.currentItem()
        if not item:
            return []
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        kind = data.get("type")
        if kind == "project":
            name = data.get("name", "")
            return [c.id for c in self._projects.get(name, [])]
        elif kind == "container":
            return [data.get("id", "")]
        # Maybe clicked on Standalone header — return all standalone
        return [c.id for c in getattr(self, "_standalone", [])]

    def _get_selected_single_id(self) -> str | None:
        item = self._tree.currentItem()
        if not item:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "container":
            return data.get("id")
        return None

    # ── Actions ──────────────────────────────────────────────────────────

    def _group_action(self, op: str):
        ids = self._get_selected_ids()
        if not ids:
            return
        fn_map = {
            "start":   self._docker.start_container,
            "stop":    self._docker.stop_container,
            "restart": self._docker.restart_container,
        }
        fn = fn_map.get(op)
        if not fn:
            return
        for cid in ids:
            w = ActionWorker(fn, cid)
            w.success.connect(lambda _: self._refresh())
            w.error.connect(self._show_error)
            self._workers.append(w)
            w.start()

    def _open_logs(self):
        cid = self._get_selected_single_id()
        if not cid:
            # If project selected, open logs for first running container
            ids = self._get_selected_ids()
            if ids:
                cid = ids[0]
        if not cid:
            return
        from src.ui.logs_dialog import LogsDialog
        dlg = LogsDialog(self._docker, cid, self)
        dlg.show()

    def _open_terminal(self):
        cid = self._get_selected_single_id()
        if not cid:
            ids = self._get_selected_ids()
            if ids:
                cid = ids[0]
        if not cid:
            return
        from src.ui.terminal_widget import ContainerTerminalDialog
        dlg = ContainerTerminalDialog(cid, self)
        dlg.show()

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
