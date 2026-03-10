import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.dirname(__file__))

# Point docker CLI (and subprocesses) at Colima's socket if it exists
_colima_sock = os.path.expanduser("~/.colima/default/docker.sock")
if os.path.exists(_colima_sock) and "DOCKER_HOST" not in os.environ:
    os.environ["DOCKER_HOST"] = f"unix://{_colima_sock}"

def _headless():
    """Start Colima in the background without launching the GUI (macOS only)."""
    if sys.platform != "darwin":
        print("Headless mode (-d) requires Colima and is only supported on macOS.", file=sys.stderr)
        sys.exit(1)
    from src.workers.colima_worker import colima_installed, colima_running, _colima_bin
    import subprocess

    if not colima_installed():
        print("colima not found. Install with: brew install colima", file=sys.stderr)
        sys.exit(1)

    if colima_running():
        print("Docker (Colima) is already running.")
        sys.exit(0)

    print("Starting Colima…")
    r = subprocess.run([_colima_bin(), "start"])
    if r.returncode == 0:
        print("Docker (Colima) started successfully.")
        sys.exit(0)
    else:
        print("colima start failed.", file=sys.stderr)
        sys.exit(r.returncode)


def _stop():
    """Stop Colima from the command line (macOS only)."""
    if sys.platform != "darwin":
        print("Stop mode (-s) requires Colima and is only supported on macOS.", file=sys.stderr)
        sys.exit(1)
    from src.workers.colima_worker import colima_installed, colima_running, _colima_bin
    import subprocess

    if not colima_installed():
        print("colima not found.", file=sys.stderr)
        sys.exit(1)

    if not colima_running():
        print("Docker (Colima) is not running.")
        sys.exit(0)

    print("Stopping Colima…")
    r = subprocess.run([_colima_bin(), "stop"])
    if r.returncode == 0:
        print("Docker (Colima) stopped.")
        sys.exit(0)
    else:
        print("colima stop failed.", file=sys.stderr)
        sys.exit(r.returncode)


_HELP = """\
DockPilot — lightweight Docker Desktop replacement

Usage:
  dockpilot [options]

Options:
  -h, --help       Show this help message and exit
  -u, --upgrade    Update DockPilot to the latest version
  -d, --headless   Start Docker (Colima) in the background, no GUI  [macOS only]
  -s, --stop       Stop Docker (Colima) from the terminal            [macOS only]

With no options, DockPilot opens the GUI.
"""


def _upgrade():
    """Pull latest code and reinstall dependencies via install.sh."""
    import subprocess
    install_sh = os.path.join(os.path.dirname(__file__), "install.sh")
    if not os.path.exists(install_sh):
        print("install.sh not found. Re-run the installer:", file=sys.stderr)
        print("  curl -sSL https://raw.githubusercontent.com/georgegozal/dockpilot/main/install.sh | bash",
              file=sys.stderr)
        sys.exit(1)
    r = subprocess.run(["bash", install_sh])
    sys.exit(r.returncode)


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(_HELP, end="")
        sys.exit(0)
    if "-u" in sys.argv or "--upgrade" in sys.argv:
        _upgrade()
    if "-d" in sys.argv or "--headless" in sys.argv:
        _headless()
    if "-s" in sys.argv or "--stop" in sys.argv:
        _stop()

    from src.app import DockPilotApp
    app = DockPilotApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
