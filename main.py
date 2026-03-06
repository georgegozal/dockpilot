import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.dirname(__file__))

# Point docker CLI (and subprocesses) at Colima's socket if it exists
_colima_sock = os.path.expanduser("~/.colima/default/docker.sock")
if os.path.exists(_colima_sock) and "DOCKER_HOST" not in os.environ:
    os.environ["DOCKER_HOST"] = f"unix://{_colima_sock}"

def _headless():
    """Start Colima in the background without launching the GUI."""
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
    """Stop Colima from the command line."""
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


def main():
    if "-d" in sys.argv or "--headless" in sys.argv:
        _headless()
    if "-s" in sys.argv or "--stop" in sys.argv:
        _stop()

    from src.app import DockPilotApp
    app = DockPilotApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
