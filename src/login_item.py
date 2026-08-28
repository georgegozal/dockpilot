"""Manage the "Open at Login" toggle across macOS and Linux.

macOS: a LaunchAgent plist in ~/Library/LaunchAgents.
Linux: an XDG autostart .desktop file in ~/.config/autostart.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BUNDLE_ID = "com.keytype.dockpilot"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _macos_app_bundle() -> Path | None:
    bundle = Path("/Applications/DockPilot.app")
    return bundle if bundle.exists() else None


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_BUNDLE_ID}.plist"


def _macos_program_args() -> list[str]:
    bundle = _macos_app_bundle()
    if bundle is not None:
        exe = bundle / "Contents" / "MacOS" / "dockpilot"
        if exe.exists():
            return [str(exe)]
    # Not installed via install.sh -- fall back to running from source.
    return [sys.executable, str(_project_root() / "main.py")]


def _linux_autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "dockpilot.desktop"


def _linux_exec_command() -> str:
    launcher = Path.home() / ".local" / "bin" / "dockpilot"
    if launcher.exists():
        return str(launcher)
    return f'"{sys.executable}" "{_project_root() / "main.py"}"'


def is_supported() -> bool:
    return sys.platform == "darwin" or sys.platform.startswith("linux")


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _macos_plist_path().exists()
    if sys.platform.startswith("linux"):
        return _linux_autostart_path().exists()
    return False


def set_enabled(enabled: bool) -> None:
    if sys.platform == "darwin":
        _set_enabled_macos(enabled)
    elif sys.platform.startswith("linux"):
        _set_enabled_linux(enabled)


def _set_enabled_macos(enabled: bool) -> None:
    plist_path = _macos_plist_path()
    if enabled:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        args_xml = "\n".join(f"        <string>{a}</string>" for a in _macos_program_args())
        plist_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            f"    <key>Label</key>\n    <string>{_BUNDLE_ID}</string>\n"
            "    <key>ProgramArguments</key>\n    <array>\n"
            f"{args_xml}\n"
            "    </array>\n"
            "    <key>RunAtLoad</key>\n    <true/>\n"
            "</dict>\n"
            "</plist>\n"
        )
        # Deliberately not calling `launchctl load` here: that would run
        # RunAtLoad immediately and spawn a second DockPilot right now.
        # macOS bootstraps ~/Library/LaunchAgents on its own at the next login.
    else:
        plist_path.unlink(missing_ok=True)


def _set_enabled_linux(enabled: bool) -> None:
    desktop_path = _linux_autostart_path()
    if enabled:
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=DockPilot\n"
            f"Exec={_linux_exec_command()}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    else:
        desktop_path.unlink(missing_ok=True)
