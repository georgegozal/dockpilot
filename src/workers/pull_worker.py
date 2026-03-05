from PyQt6.QtCore import QThread, pyqtSignal
import json


class PullWorker(QThread):
    """Pulls a Docker image and streams progress."""

    progress = pyqtSignal(str)   # status line
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, docker_client, image: str, tag: str = "latest"):
        super().__init__()
        self._docker = docker_client
        self._image = image
        self._tag = tag

    def run(self):
        try:
            for line in self._docker.raw.api.pull(
                self._image, tag=self._tag, stream=True, decode=True
            ):
                status = line.get("status", "")
                detail = line.get("progressDetail", {})
                prog = ""
                if detail.get("total"):
                    current = detail.get("current", 0)
                    total = detail.get("total", 1)
                    prog = f"  {current / (1024*1024):.1f}/{total / (1024*1024):.1f} MB"
                layer = line.get("id", "")
                msg = f"[{layer}] {status}{prog}" if layer else status
                self.progress.emit(msg)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
