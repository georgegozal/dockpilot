from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QFrame, QHeaderView,
    QAbstractItemView, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from src.docker_client import DockerClient
from src.workers.action_worker import ActionWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
RED      = "#f85149"
YELLOW   = "#ffb900"

COLS = ["Repository", "Tag", "Image ID", "Size", "Created"]
COL_REPO    = 0
COL_TAG     = 1
COL_ID      = 2
COL_SIZE    = 3
COL_CREATED = 4


def _fmt_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


class ImagesPanel(QWidget):
    def __init__(self, docker: DockerClient, main_window=None):
        super().__init__()
        self._docker = docker
        self._main_window = main_window
        self._images: list = []
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

        title = QLabel("Images")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        tb.addWidget(title)
        tb.addStretch()

        self._all_check = QCheckBox("Show dangling")
        self._all_check.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        self._all_check.toggled.connect(self._refresh)
        tb.addWidget(self._all_check)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter images…")
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
        tb.addWidget(self._search)

        for label, slot in [("Refresh", self._refresh), ("Pull image…", self._open_pull)]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = ACCENT if label == "Pull image…" else BG
            border = "none" if label == "Pull image…" else f"1px solid {BORDER}"
            fg = "white" if label == "Pull image…" else TEXT
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: {fg};
                    border: {border};
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
        hdr.setSectionResizeMode(COL_REPO,    QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_TAG,     QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ID,      QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_SIZE,    QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_CREATED, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(COL_REPO,  280)
        self._table.setColumnWidth(COL_TAG,   120)
        self._table.setColumnWidth(COL_ID,    110)
        self._table.setColumnWidth(COL_SIZE,   90)

        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table, 1)

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
            b.setFixedWidth(90)
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

        self._btn_inspect = _btn("Inspect", "#555")
        self._btn_remove  = _btn("Remove",  RED)
        self._btn_prune   = _btn("Prune dangling", YELLOW)
        self._btn_prune.setFixedWidth(130)

        for btn in [self._btn_inspect, self._btn_remove]:
            btn.setEnabled(False)
            ab.addWidget(btn)
        ab.addWidget(self._btn_prune)

        self._btn_inspect.clicked.connect(self._open_inspect)
        self._btn_remove.clicked.connect(self._remove_image)
        self._btn_prune.clicked.connect(self._prune_images)

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
        timer.start(10000)

    def _refresh(self):
        self._images = self._docker.images(all=self._all_check.isChecked())
        self._populate_table()

    def _populate_table(self):
        flt = self._search.text().lower()
        rows = []
        for img in self._images:
            tags = img.tags or ["<none>:<none>"]
            for tag in tags:
                repo, t = tag.rsplit(":", 1) if ":" in tag else (tag, "latest")
                if flt and flt not in repo.lower() and flt not in t.lower():
                    continue
                rows.append((img, repo, t))

        self._table.setRowCount(len(rows))
        for row, (img, repo, tag) in enumerate(rows):
            short_id = img.short_id.replace("sha256:", "")
            size     = _fmt_size(img.attrs.get("Size", 0))
            created  = str(img.attrs.get("Created", ""))[:10]

            def cell(text: str, color: str = TEXT) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                item.setData(Qt.ItemDataRole.UserRole, img.id)
                return item

            self._table.setItem(row, COL_REPO,    cell(repo))
            self._table.setItem(row, COL_TAG,     cell(tag, ACCENT if tag == "latest" else TEXT))
            self._table.setItem(row, COL_ID,      cell(short_id, TEXT_DIM))
            self._table.setItem(row, COL_SIZE,    cell(size))
            self._table.setItem(row, COL_CREATED, cell(created))
            self._table.setRowHeight(row, 34)

    def _apply_filter(self):
        self._populate_table()

    # ── Selection ────────────────────────────────────────────────────────

    def _selected_image_id(self) -> str | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), COL_REPO)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self):
        iid = self._selected_image_id()
        has = iid is not None
        self._btn_inspect.setEnabled(has)
        self._btn_remove.setEnabled(has)
        if has:
            row = self._table.selectionModel().selectedRows()[0].row()
            repo = self._table.item(row, COL_REPO).text()
            tag  = self._table.item(row, COL_TAG).text()
            size = self._table.item(row, COL_SIZE).text()
            self._info_label.setText(f"{repo}:{tag}  ({size})")
        else:
            self._info_label.setText("")

    # ── Actions ──────────────────────────────────────────────────────────

    def _remove_image(self):
        iid = self._selected_image_id()
        if not iid:
            return
        reply = QMessageBox.question(
            self, "Remove image",
            f"Remove image {iid[:12]}?\n\nThis will fail if the image is in use.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.remove_image, iid, force=False)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _prune_images(self):
        reply = QMessageBox.question(
            self, "Prune dangling images",
            "Remove all dangling (untagged) images?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        w = ActionWorker(self._docker.prune_images)
        w.success.connect(lambda _: self._refresh())
        w.error.connect(self._show_error)
        self._workers.append(w)
        w.start()

    def _open_inspect(self):
        iid = self._selected_image_id()
        if not iid:
            return
        from src.ui.inspect_dialog import InspectDialog
        try:
            data = self._docker.inspect_image(iid)
        except Exception as e:
            self._show_error(str(e))
            return
        dlg = InspectDialog("Image inspect", data, self)
        dlg.show()

    def _open_pull(self):
        from src.ui.pull_dialog import PullDialog
        dlg = PullDialog(self._docker, self)
        dlg.finished.connect(lambda _: self._refresh())
        dlg.exec()

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
