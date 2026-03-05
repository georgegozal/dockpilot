from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush

from src.docker_client import DockerClient
from src.workers.stats_worker import StatsWorker

BG       = "#1e1e1e"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"
YELLOW   = "#ffb900"


def _fmt_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class MiniGraph(QWidget):
    """Simple sparkline graph for one metric."""

    def __init__(self, color: str = ACCENT, max_val: float = 100.0, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._max_val = max_val
        self._values: list[float] = []
        self._cap = 60
        self.setFixedHeight(60)
        self.setMinimumWidth(200)

    def push(self, value: float):
        self._values.append(value)
        if len(self._values) > self._cap:
            self._values.pop(0)
        self.update()

    def paintEvent(self, event):
        if not self._values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(self._values)

        # Background
        painter.fillRect(0, 0, w, h, QColor(SURFACE))

        # Grid line at 50%
        painter.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, h // 2, w, h // 2)

        if n < 2:
            return

        # Line
        painter.setPen(QPen(self._color, 2))
        step = w / (self._cap - 1)
        mx = max(self._max_val, max(self._values) or 1)

        points = []
        for i, v in enumerate(self._values):
            x = int((i + (self._cap - n)) * step)
            y = int(h - (v / mx) * h)
            points.append((x, y))

        for i in range(len(points) - 1):
            painter.drawLine(points[i][0], points[i][1], points[i+1][0], points[i+1][1])

        # Fill under line
        fill_color = QColor(self._color)
        fill_color.setAlpha(40)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(Qt.PenStyle.NoPen)
        from PyQt6.QtGui import QPolygon
        from PyQt6.QtCore import QPoint
        poly_pts = [QPoint(points[0][0], h)] + \
                   [QPoint(x, y) for x, y in points] + \
                   [QPoint(points[-1][0], h)]
        painter.drawPolygon(*poly_pts)


class StatRow(QFrame):
    """One metric row: label + value + optional graph."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SURFACE}; border-radius: 6px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; font-weight: bold;")
        header.addWidget(lbl)
        header.addStretch()
        self._value_label = QLabel("—")
        self._value_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        header.addWidget(self._value_label)
        layout.addLayout(header)

        self._graph = MiniGraph(color, parent=self)
        layout.addWidget(self._graph)

    def update_value(self, text: str, graph_val: float):
        self._value_label.setText(text)
        self._graph.push(graph_val)


class StatsDialog(QDialog):
    def __init__(self, docker: DockerClient, container_id: str, parent=None):
        super().__init__(parent)
        self._docker = docker
        self._container_id = container_id
        self._worker: StatsWorker | None = None

        c = docker.get_container(container_id)
        name = c.name if c else container_id[:12]
        self.setWindowTitle(f"Stats — {name}")
        self.resize(520, 480)
        self.setStyleSheet(f"background: {BG};")
        self._build_ui()
        self._start_stats()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(f"Live stats  ·  {self._container_id[:12]}")
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        self._cpu_row = StatRow("CPU Usage", ACCENT)
        self._mem_row = StatRow("Memory",    GREEN)
        self._net_row = StatRow("Network I/O", YELLOW)
        self._blk_row = StatRow("Block I/O",  RED)

        for row in [self._cpu_row, self._mem_row, self._net_row, self._blk_row]:
            layout.addWidget(row)

        layout.addStretch()

        self._status = QLabel("Connecting…")
        self._status.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self._status)

    def _start_stats(self):
        self._worker = StatsWorker(self._docker, self._container_id)
        self._worker.stats_updated.connect(self._on_stats)
        self._worker.error.connect(lambda cid, e: self._status.setText(f"Error: {e}"))
        self._worker.start()

    def _on_stats(self, cid: str, stats: dict):
        cpu  = stats["cpu_pct"]
        mem  = stats["mem_usage"]
        mlim = stats["mem_limit"]
        mpct = stats["mem_pct"]
        rx   = stats["net_rx"]
        tx   = stats["net_tx"]
        br   = stats["block_read"]
        bw   = stats["block_write"]

        self._cpu_row.update_value(f"{cpu:.1f}%", cpu)
        self._mem_row.update_value(
            f"{_fmt_bytes(mem)} / {_fmt_bytes(mlim)}  ({mpct:.1f}%)",
            mpct,
        )
        self._net_row.update_value(
            f"RX {_fmt_bytes(rx)}  TX {_fmt_bytes(tx)}",
            (rx + tx) / (1024 * 1024),
        )
        self._blk_row.update_value(
            f"R {_fmt_bytes(br)}  W {_fmt_bytes(bw)}",
            (br + bw) / (1024 * 1024),
        )
        self._status.setText("Live")

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)
