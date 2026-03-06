from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QFrame, QHeaderView,
    QAbstractItemView, QMessageBox, QInputDialog, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from src.docker_client import DockerClient
from src.workers.action_worker import ActionWorker, FetchWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
RED      = "#f85149"
YELLOW   = "#ffb900"

COLS = ["Name", "Driver", "Scope", "Subnet", "Gateway", "Containers", "ID"]
COL_NAME       = 0
COL_DRIVER     = 1
COL_SCOPE      = 2
COL_SUBNET     = 3
COL_GATEWAY    = 4
COL_CONTAINERS = 5
COL_ID         = 6

BUILT_IN = {"bridge", "host", "none"}


class NetworksPanel(QWidget):
    def __init__(self, docker: DockerClient, main_window=None):
        super().__init__()
        self._docker = docker
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

        title = QLabel("Networks")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        tb.addWidget(title)
        tb.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter networks…")
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
        self._search.textChanged.connect(self._populate_table)
        tb.addWidget(self._search)

        for label, slot, color, fg in [
            ("Refresh",         self._refresh,          BG,     TEXT),
            ("Create network…", self._create_network,   ACCENT, "white"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: {fg};
                    border: {"none" if color != BG else f"1px solid {BORDER}"};
                    border-radius: 4px;
                    padding: 0 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background: {color}cc; }}
            """)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        layout.addWidget(toolbar)

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
            QTableWidget::item:selected {{ background: {ACCENT}44; }}
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
        self._table.verticalHeader().setVisible(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NAME,       QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_DRIVER,     QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_SCOPE,      QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_SUBNET,     QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_GATEWAY,    QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_CONTAINERS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ID,         QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(COL_NAME,       200)
        self._table.setColumnWidth(COL_DRIVER,      80)
        self._table.setColumnWidth(COL_SCOPE,       70)
        self._table.setColumnWidth(COL_SUBNET,     140)
        self._table.setColumnWidth(COL_GATEWAY,    130)
        self._table.setColumnWidth(COL_CONTAINERS,  90)

        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table, 1)

        # Action bar
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        action_bar.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        ab = QHBoxLayout(action_bar)
        ab.setContentsMargins(16, 8, 16, 8)
        ab.setSpacing(8)

        def _btn(label, color, width=90):
            c = color if len(color) != 4 else f"#{color[1]*2}{color[2]*2}{color[3]*2}"
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setFixedWidth(width)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {c};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {c}cc; }}
                QPushButton:disabled {{ background: #444444; color: #777777; }}
            """)
            return b

        self._btn_inspect = _btn("Inspect", "#555555")
        self._btn_remove  = _btn("Remove",  RED)
        self._btn_prune   = _btn("Prune unused", YELLOW, 120)

        for btn in [self._btn_inspect, self._btn_remove]:
            btn.setEnabled(False)
            ab.addWidget(btn)
        ab.addWidget(self._btn_prune)

        self._btn_inspect.clicked.connect(self._open_inspect)
        self._btn_remove.clicked.connect(self._remove_network)
        self._btn_prune.clicked.connect(self._prune_networks)

        ab.addStretch()
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        ab.addWidget(self._info_label)
        layout.addWidget(action_bar)

    def _start_auto_refresh(self):
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(10000)

    def _refresh(self):
        if getattr(self, "_fetch_worker", None) and self._fetch_worker.isRunning():
            return
        self._fetch_worker = FetchWorker(self._docker.networks, self)
        self._fetch_worker.result.connect(self._on_fetched)
        self._fetch_worker.start()

    def _on_fetched(self, networks):
        self._networks = networks
        self._populate_table()

    def _populate_table(self):
        flt = self._search.text().lower()
        networks = getattr(self, "_networks", [])
        rows = [n for n in networks if not flt or flt in n.name.lower()]

        self._table.setRowCount(len(rows))
        for row, n in enumerate(rows):
            attrs  = n.attrs or {}
            driver = attrs.get("Driver", "")
            scope  = attrs.get("Scope", "")
            ipam   = attrs.get("IPAM", {})
            configs = ipam.get("Config", [{}])
            subnet  = configs[0].get("Subnet", "") if configs else ""
            gateway = configs[0].get("Gateway", "") if configs else ""
            containers = len(attrs.get("Containers", {}))
            short_id = n.id[:12] if n.id else ""

            is_builtin = n.name in BUILT_IN
            fg = TEXT_DIM if is_builtin else TEXT

            def cell(text: str) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setForeground(QColor(fg))
                item.setData(Qt.ItemDataRole.UserRole, n.id)
                return item

            self._table.setItem(row, COL_NAME,       cell(n.name))
            self._table.setItem(row, COL_DRIVER,     cell(driver))
            self._table.setItem(row, COL_SCOPE,      cell(scope))
            self._table.setItem(row, COL_SUBNET,     cell(subnet))
            self._table.setItem(row, COL_GATEWAY,    cell(gateway))
            self._table.setItem(row, COL_CONTAINERS, cell(str(containers)))
            self._table.setItem(row, COL_ID,         cell(short_id))
            self._table.setRowHeight(row, 34)

    def _selected_network_id(self) -> str | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self):
        nid = self._selected_network_id()
        has = nid is not None
        self._btn_inspect.setEnabled(has)
        # Disallow removing built-in networks
        if has:
            row = self._table.selectionModel().selectedRows()[0].row()
            name = self._table.item(row, COL_NAME).text()
            self._btn_remove.setEnabled(name not in BUILT_IN)
            self._info_label.setText(name)
        else:
            self._btn_remove.setEnabled(False)
            self._info_label.setText("")

    def _create_network(self):
        name, ok = QInputDialog.getText(self, "Create network", "Network name:")
        if not ok or not name.strip():
            return
        w = ActionWorker(self._docker.create_network, name.strip())
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _remove_network(self):
        nid = self._selected_network_id()
        if not nid:
            return
        rows = self._table.selectionModel().selectedRows()
        name = self._table.item(rows[0].row(), COL_NAME).text() if rows else nid[:12]
        reply = QMessageBox.question(
            self, "Remove network",
            f"Remove network '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.remove_network, nid)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _prune_networks(self):
        reply = QMessageBox.question(
            self, "Prune unused networks",
            "Remove all networks not used by any container?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.prune_networks)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _open_inspect(self):
        nid = self._selected_network_id()
        if not nid:
            return
        from src.ui.inspect_dialog import InspectDialog
        try:
            data = self._docker.inspect_network(nid)
        except Exception as e:
            self._show_error(str(e))
            return
        dlg = InspectDialog(f"Network inspect", data, self)
        dlg.show()

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
