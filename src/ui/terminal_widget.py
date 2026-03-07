from __future__ import annotations
import os
import pty
import fcntl
import struct
import termios
import subprocess
import signal
import shutil

# Common docker binary locations on macOS / Linux (fallback if not in PATH)
_DOCKER_FALLBACK_PATHS = [
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
    "/Applications/Docker.app/Contents/Resources/bin/docker",
    "/usr/bin/docker",
]


def _find_docker() -> str | None:
    """Locate the docker binary via PATH then common macOS/Linux locations."""
    found = shutil.which("docker")
    if found:
        return found
    for path in _DOCKER_FALLBACK_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


import pyte
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QPlainTextEdit, QFrame, QWidget,
)
from PyQt6.QtCore import Qt, QSocketNotifier, QTimer
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QKeyEvent,
    QTextCharFormat, QFontMetricsF,
)

BG       = "#1a1a1a"
SURFACE  = "#252526"
BORDER   = "#3e3e42"
TEXT     = "#cccccc"
TEXT_DIM = "#888888"
ACCENT   = "#0078d4"
GREEN    = "#16c60c"
RED      = "#f85149"

# ── ANSI 256-colour palette (first 16 standard colours) ──────────────────────
_ANSI16 = [
    "#000000", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
]


def _resolve_color(spec, default: str) -> str:
    if spec == "default" or spec is None:
        return default
    if isinstance(spec, int):
        if 0 <= spec < 16:
            return _ANSI16[spec]
        # 256-colour cube / grayscale
        if 16 <= spec < 232:
            n = spec - 16
            b = n % 6; n //= 6
            g = n % 6; r = n // 6
            return "#{:02x}{:02x}{:02x}".format(r * 51, g * 51, b * 51)
        if 232 <= spec < 256:
            v = 8 + (spec - 232) * 10
            return "#{:02x}{:02x}{:02x}".format(v, v, v)
    if isinstance(spec, tuple) and len(spec) == 3:
        return "#{:02x}{:02x}{:02x}".format(*spec)
    return default


class _Screen(pyte.HistoryScreen):
    """pyte screen with SGR private-kwarg crash fix."""

    def __init__(self, cols: int, rows: int):
        super().__init__(cols, rows, history=2000, ratio=0.3)
        try:
            self.set_mode(pyte.modes.LNM)
        except Exception:
            pass

    def draw(self, *args, **kwargs):
        kwargs.pop("private", None)
        try:
            super().draw(*args, **kwargs)
        except Exception:
            pass


class TerminalView(QPlainTextEdit):
    """Keyboard-capturing terminal view."""

    def __init__(self, widget: "ContainerTerminalWidget"):
        super().__init__()
        self._tw = widget
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        font = QFont("Menlo, Monaco, Consolas, Courier New", 13)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {BG};
                color: {TEXT};
                border: none;
                padding: 4px;
                selection-background-color: {ACCENT}55;
            }}
        """)
        self.setCursorWidth(2)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def event(self, event):
        # Intercept Tab/Backtab before Qt uses them for focus-chain navigation
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.keyPressEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        self._tw._handle_key(event)

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(800, 500)


class ContainerTerminalWidget(QWidget):
    """
    Interactive terminal for docker exec sessions.
    Uses pty + subprocess + pyte for full VT100 emulation.
    """

    def __init__(self, container_id: str, parent=None):
        super().__init__(parent)
        self._container_id = container_id
        self._master_fd: int | None = None
        self._process: subprocess.Popen | None = None
        self._notifier: QSocketNotifier | None = None
        self._cols = 80
        self._rows = 24
        self._screen = _Screen(self._cols, self._rows)
        self._stream = pyte.ByteStream(self._screen)
        self._dead = False

        self._build_ui()
        self._start_exec()

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(38)
        header.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        hb = QHBoxLayout(header)
        hb.setContentsMargins(12, 4, 12, 4)
        hb.setSpacing(8)

        self._title_label = QLabel(f"Terminal  {self._container_id[:12]}")
        self._title_label.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        hb.addWidget(self._title_label)
        hb.addStretch()

        self._status_label = QLabel("Connecting…")
        self._status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        hb.addWidget(self._status_label)

        reconnect_btn = QPushButton("Reconnect")
        reconnect_btn.setFixedHeight(24)
        reconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reconnect_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {ACCENT}cc; }}
        """)
        reconnect_btn.clicked.connect(self._reconnect)
        hb.addWidget(reconnect_btn)
        layout.addWidget(header)

        # Terminal view
        self._view = TerminalView(self)
        layout.addWidget(self._view, 1)

    # ── Exec ────────────────────────────────────────────────────────────

    def _start_exec(self):
        self._dead = False

        docker_bin = _find_docker()
        if not docker_bin:
            self._status_label.setText("docker CLI not found — add it to PATH")
            self._status_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
            return

        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd

        self._set_pty_size(self._rows, self._cols)

        # Standard LS_COLORS for directory/file-type coloring
        _LS_COLORS = (
            "di=1;34:ln=1;36:so=1;35:pi=1;33:ex=1;32:"
            "bd=1;33;40:cd=1;33;40:su=1;31:sg=1;31:"
            "tw=1;32:ow=1;34"
        )

        # Build env: inherit current env so docker can find its socket/config
        env = os.environ.copy()
        env["TERM"]          = "xterm-256color"
        env["COLORTERM"]     = "truecolor"
        env["CLICOLOR"]      = "1"
        env["CLICOLOR_FORCE"]= "1"
        env["LS_COLORS"]     = _LS_COLORS

        # Try bash (interactive = sources /etc/bash.bashrc + ~/.bashrc color aliases)
        # then ash/sh without -i (they don't have the same interactive sourcing)
        launched = False
        last_error = ""
        for shell, shell_args in [
            ("/bin/bash", ["-i"]),
            ("/bin/ash",  []),
            ("/bin/sh",   []),
        ]:
            try:
                self._process = subprocess.Popen(
                    [docker_bin, "exec", "-it",
                     "-e", "TERM=xterm-256color",
                     "-e", "COLORTERM=truecolor",
                     "-e", "CLICOLOR=1",
                     "-e", "CLICOLOR_FORCE=1",
                     "-e", f"LS_COLORS={_LS_COLORS}",
                     self._container_id, shell] + shell_args,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                    preexec_fn=os.setsid,
                    env=env,
                )
                launched = True
                break
            except Exception as exc:
                last_error = str(exc)
                continue

        os.close(slave_fd)

        if not launched:
            msg = f"Failed to exec: {last_error}" if last_error else "Failed to launch exec"
            self._status_label.setText(msg)
            self._status_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
            return

        # Non-blocking read on master fd
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self._notifier = QSocketNotifier(master_fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read_output)

        # Process monitor
        self._monitor = QTimer(self)
        self._monitor.timeout.connect(self._check_process)
        self._monitor.start(1000)

        self._status_label.setText("Connected")
        self._view.setFocus()

    def _set_pty_size(self, rows: int, cols: int):
        if self._master_fd is None:
            return
        try:
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:
            pass

    # ── I/O ─────────────────────────────────────────────────────────────

    def _read_output(self):
        try:
            data = os.read(self._master_fd, 65536)
        except (OSError, BlockingIOError):
            return
        if data:
            self._stream.feed(data)
            self._render()

    def _write(self, data: bytes):
        if self._master_fd is None or self._dead:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def _handle_key(self, event: QKeyEvent):
        key    = event.key()
        mods   = event.modifiers()
        text   = event.text()
        ctrl   = mods & Qt.KeyboardModifier.ControlModifier
        shift  = mods & Qt.KeyboardModifier.ShiftModifier

        # Copy (Ctrl+C when text selected, Ctrl+Shift+C always)
        if ctrl and shift and key == Qt.Key.Key_C:
            self._view.copy()
            return
        if ctrl and shift and key == Qt.Key.Key_V:
            from PyQt6.QtWidgets import QApplication
            clip = QApplication.clipboard().text()
            self._write(clip.encode("utf-8", errors="replace"))
            return

        # Arrow keys
        arrows = {
            Qt.Key.Key_Up:    b"\x1b[A",
            Qt.Key.Key_Down:  b"\x1b[B",
            Qt.Key.Key_Right: b"\x1b[C",
            Qt.Key.Key_Left:  b"\x1b[D",
        }
        if key in arrows:
            self._write(arrows[key])
            return

        # Function keys
        fkeys = {
            Qt.Key.Key_F1:  b"\x1bOP",  Qt.Key.Key_F2:  b"\x1bOQ",
            Qt.Key.Key_F3:  b"\x1bOR",  Qt.Key.Key_F4:  b"\x1bOS",
            Qt.Key.Key_F5:  b"\x1b[15~",Qt.Key.Key_F6:  b"\x1b[17~",
            Qt.Key.Key_F7:  b"\x1b[18~",Qt.Key.Key_F8:  b"\x1b[19~",
            Qt.Key.Key_F9:  b"\x1b[20~",Qt.Key.Key_F10: b"\x1b[21~",
            Qt.Key.Key_F11: b"\x1b[23~",Qt.Key.Key_F12: b"\x1b[24~",
        }
        if key in fkeys:
            self._write(fkeys[key])
            return

        # Special keys
        specials = {
            Qt.Key.Key_Return:   b"\r",
            Qt.Key.Key_Enter:    b"\r",
            Qt.Key.Key_Backspace:b"\x7f",
            Qt.Key.Key_Delete:   b"\x1b[3~",
            Qt.Key.Key_Tab:      b"\t",
            Qt.Key.Key_Backtab:  b"\x1b[Z",
            Qt.Key.Key_Home:     b"\x1b[H",
            Qt.Key.Key_End:      b"\x1b[F",
            Qt.Key.Key_PageUp:   b"\x1b[5~",
            Qt.Key.Key_PageDown: b"\x1b[6~",
            Qt.Key.Key_Insert:   b"\x1b[2~",
            Qt.Key.Key_Escape:   b"\x1b",
        }
        if key in specials:
            self._write(specials[key])
            return

        # Ctrl+key combinations
        if ctrl and not shift:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                self._write(bytes([key - Qt.Key.Key_A + 1]))
                return
            if key == Qt.Key.Key_BracketLeft:
                self._write(b"\x1b")
                return
            if key == Qt.Key.Key_Backslash:
                self._write(b"\x1c")
                return

        if text:
            self._write(text.encode("utf-8", errors="replace"))

    # ── Render ───────────────────────────────────────────────────────────

    def _render(self):
        """Re-render the pyte screen into QPlainTextEdit with colour."""
        screen = self._screen
        doc_lines = []

        # Build plain text first (for block count check)
        for y in range(screen.lines):
            line_chars = screen.buffer[y]
            line = "".join(
                char.data if char.data else " "
                for x in range(screen.columns)
                for char in [line_chars[x]]
            )
            doc_lines.append(line.rstrip())

        # We'll render with colours using setHtml
        cur_x = screen.cursor.x
        cur_y = screen.cursor.y
        html_lines = []
        for y in range(screen.lines):
            line_chars = screen.buffer[y]
            spans = []
            for x in range(screen.columns):
                char = line_chars[x]
                ch   = char.data if char.data else " "
                fg   = _resolve_color(char.fg, TEXT)
                bg   = _resolve_color(char.bg, BG)
                bold = char.bold
                ul   = char.underscore
                # Draw block cursor by inverting colors at cursor position
                if x == cur_x and y == cur_y and not self._dead:
                    fg, bg = BG, "#e0e0e0"
                style = f"color:{fg};background:{bg};"
                if bold:
                    style += "font-weight:bold;"
                if ul:
                    style += "text-decoration:underline;"
                ch_escaped = (ch
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace(" ", "&nbsp;"))
                spans.append(f'<span style="{style}">{ch_escaped}</span>')
            html_lines.append("".join(spans))

        html = f'<pre style="margin:0;padding:0;font-family:\'Menlo\',\'Monaco\',monospace;font-size:13px;">{"<br>".join(html_lines)}</pre>'

        # Temporarily block signals to avoid cursor jumps
        self._view.blockSignals(True)
        scrollbar = self._view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5

        self._view.clear()
        self._view.appendHtml(html)

        # Position cursor
        try:
            cursor = self._view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(screen.cursor.y):
                cursor.movePosition(QTextCursor.MoveOperation.Down)
            for _ in range(screen.cursor.x):
                cursor.movePosition(QTextCursor.MoveOperation.Right)
            self._view.setTextCursor(cursor)
        except Exception:
            pass

        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

        self._view.blockSignals(False)

    # ── Process monitor ──────────────────────────────────────────────────

    def _check_process(self):
        if self._process and self._process.poll() is not None:
            self._on_process_exit()

    def _on_process_exit(self):
        if self._dead:
            return
        self._dead = True
        self._monitor.stop()
        if self._notifier:
            self._notifier.setEnabled(False)
        exit_code = self._process.returncode if self._process else 0
        self._status_label.setText(f"Exited (code {exit_code})")
        self._status_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        # Close the dialog after a brief pause so the exit is visible
        QTimer.singleShot(400, self.window().close)

    def _reconnect(self):
        self._cleanup()
        self._screen = _Screen(self._cols, self._rows)
        self._stream = pyte.ByteStream(self._screen)
        self._view.clear()
        self._status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self._start_exec()

    def _cleanup(self):
        if self._notifier:
            self._notifier.setEnabled(False)
            self._notifier = None
        if hasattr(self, "_monitor") and self._monitor.isActive():
            self._monitor.stop()
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                pass
            self._process = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except Exception:
                pass
            self._master_fd = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalc_size()

    def _recalc_size(self):
        fm = QFontMetricsF(self._view.font())
        char_w = fm.horizontalAdvance("M")
        char_h = fm.height()
        if char_w <= 0 or char_h <= 0:
            return
        w = self._view.viewport().width()
        h = self._view.viewport().height()
        cols = max(20, int(w / char_w))
        rows = max(5, int(h / char_h))
        if cols != self._cols or rows != self._rows:
            self._cols = cols
            self._rows = rows
            self._screen.resize(rows, cols)
            self._set_pty_size(rows, cols)

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)


# ── Dialog wrapper ────────────────────────────────────────────────────────────

class ContainerTerminalDialog(QDialog):
    def __init__(self, container_id: str, parent=None):
        super().__init__(parent)
        from src.docker_client import DockerClient
        self.setWindowTitle(f"Terminal — {container_id[:12]}")
        self.resize(900, 600)
        self.setStyleSheet(f"background: {BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._term = ContainerTerminalWidget(container_id, self)
        layout.addWidget(self._term)

    def closeEvent(self, event):
        self._term.closeEvent(event)
        super().closeEvent(event)
