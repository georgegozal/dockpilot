import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.dirname(__file__))

# Point docker CLI (and subprocesses) at Colima's socket if it exists
_colima_sock = os.path.expanduser("~/.colima/default/docker.sock")
if os.path.exists(_colima_sock) and "DOCKER_HOST" not in os.environ:
    os.environ["DOCKER_HOST"] = f"unix://{_colima_sock}"

from src.app import DockPilotApp


def main():
    app = DockPilotApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
