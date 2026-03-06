from __future__ import annotations

import shutil
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal


def _colima_bin() -> str | None:
    """Return full path to colima binary, or None if not installed."""
    p = shutil.which("colima")
    if p:
        return p
    for candidate in ("/opt/homebrew/bin/colima", "/usr/local/bin/colima"):
        import os
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


class ColimaStartWorker(QThread):
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def run(self):
        bin_ = _colima_bin()
        if not bin_:
            self.error.emit("colima not found — install with: brew install colima")
            return
        try:
            r = subprocess.run(
                [bin_, "start"],
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
