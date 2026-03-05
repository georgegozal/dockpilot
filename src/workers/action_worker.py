from PyQt6.QtCore import QThread, pyqtSignal


class ActionWorker(QThread):
    """Generic worker for one-shot Docker actions (start, stop, remove, etc.)."""

    success = pyqtSignal(str)   # success message or empty string
    error = pyqtSignal(str)     # error message

    def __init__(self, action, *args, **kwargs):
        super().__init__()
        self._action = action
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._action(*self._args, **self._kwargs)
            self.success.emit(str(result) if result is not None else "")
        except Exception as e:
            self.error.emit(str(e))
