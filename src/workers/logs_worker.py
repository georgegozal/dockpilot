from PyQt6.QtCore import QThread, pyqtSignal


class LogsWorker(QThread):
    """Streams container logs and emits them line-by-line."""

    new_data = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, docker_client, container_id: str, tail: int = 500):
        super().__init__()
        self._docker = docker_client
        self._container_id = container_id
        self._tail = tail
        self._running = True

    def run(self):
        try:
            stream = self._docker.container_logs(
                self._container_id,
                tail=self._tail,
                stream=True,
                follow=True,
                timestamps=True,
            )
            for chunk in stream:
                if not self._running:
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                self.new_data.emit(text)
        except Exception as e:
            if self._running:
                self.error.emit(str(e))

    def stop(self):
        self._running = False
