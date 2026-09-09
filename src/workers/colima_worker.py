from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QSettings


# Colima's own defaults (colima start --help / embedded template).
DEFAULT_CPU = 2
DEFAULT_MEMORY = 2  # GiB
DEFAULT_DISK = 100  # GiB

_SETTINGS_ORG = "DockPilot"
_SETTINGS_APP = "DockPilot"
_KEY_CPU = "colima_cpu"
_KEY_MEMORY = "colima_memory"
_KEY_DISK = "colima_disk"


def _colima_bin() -> str | None:
    """Return full path to colima binary, or None if not installed."""
    p = shutil.which("colima")
    if p:
        return p
    for candidate in ("/opt/homebrew/bin/colima", "/usr/local/bin/colima"):
        if os.path.isfile(candidate):
            return candidate
    return None


def colima_installed() -> bool:
    return _colima_bin() is not None


def colima_running() -> bool:
    """Return True if colima is currently running."""
    bin_ = _colima_bin()
    if not bin_:
        return False
    try:
        r = subprocess.run([bin_, "status"], capture_output=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def _colima_yaml_path() -> Path:
    return Path.home() / ".colima" / "default" / "colima.yaml"


def read_colima_resources() -> tuple[int, int, int]:
    """Read cpu / memory / disk from Colima's profile YAML, or return Colima defaults."""
    cpu, memory, disk = DEFAULT_CPU, DEFAULT_MEMORY, DEFAULT_DISK
    path = _colima_yaml_path()
    if not path.is_file():
        return cpu, memory, disk
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return cpu, memory, disk

    # Top-level keys only (ignore indented nested blocks).
    for key, cast in (("cpu", int), ("memory", float), ("disk", int)):
        m = re.search(rf"(?m)^{key}:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text)
        if not m:
            continue
        try:
            value = cast(m.group(1))
        except ValueError:
            continue
        if key == "cpu":
            cpu = max(1, int(value))
        elif key == "memory":
            memory = max(1, int(round(float(value))))
        else:
            disk = max(1, int(value))
    return cpu, memory, disk


def get_preferred_resources() -> tuple[int, int, int]:
    """DockPilot prefs if set, else Colima YAML / Colima defaults."""
    yaml_cpu, yaml_mem, yaml_disk = read_colima_resources()
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    cpu = int(s.value(_KEY_CPU, yaml_cpu))
    memory = int(s.value(_KEY_MEMORY, yaml_mem))
    disk = int(s.value(_KEY_DISK, yaml_disk))
    return max(1, cpu), max(1, memory), max(1, disk)


def save_preferred_resources(cpu: int, memory: int, disk: int) -> None:
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    s.setValue(_KEY_CPU, int(cpu))
    s.setValue(_KEY_MEMORY, int(memory))
    s.setValue(_KEY_DISK, int(disk))
    s.sync()


def colima_start_args(cpu: int | None = None, memory: int | None = None,
                      disk: int | None = None) -> list[str]:
    """Build `colima start …` argv including resource flags."""
    bin_ = _colima_bin()
    if not bin_:
        raise FileNotFoundError("colima not found")
    if cpu is None or memory is None or disk is None:
        pref_cpu, pref_mem, pref_disk = get_preferred_resources()
        cpu = pref_cpu if cpu is None else cpu
        memory = pref_mem if memory is None else memory
        disk = pref_disk if disk is None else disk
    return [
        bin_, "start",
        "--cpu", str(int(cpu)),
        "--memory", str(int(memory)),
        "--disk", str(int(disk)),
    ]


class ColimaStartWorker(QThread):
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, parent=None, cpu: int | None = None,
                 memory: int | None = None, disk: int | None = None):
        super().__init__(parent)
        self._cpu = cpu
        self._memory = memory
        self._disk = disk

    def run(self):
        if not _colima_bin():
            self.error.emit("colima not found — install with: brew install colima")
            return
        try:
            cmd = colima_start_args(self._cpu, self._memory, self._disk)
            r = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode == 0:
                self.success.emit()
            else:
                msg = (r.stderr or r.stdout).strip()
                self.error.emit(msg or "colima start failed")
        except subprocess.TimeoutExpired:
            self.error.emit("Colima start timed out (3 min).")
        except Exception as e:
            self.error.emit(str(e))


class ColimaStopWorker(QThread):
    finished = pyqtSignal()

    def run(self):
        bin_ = _colima_bin()
        if bin_:
            try:
                subprocess.run([bin_, "stop"], capture_output=True, timeout=60)
            except Exception:
                pass
        self.finished.emit()
