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


class FetchWorker(QThread):
    """Runs a callable in a background thread and emits the result.

    Prevents Docker API calls from blocking the main (UI) thread.
    """

    result = pyqtSignal(object)
    error  = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.result.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))
