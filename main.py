import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.dirname(__file__))

from src.app import DockPilotApp


def main():
    app = DockPilotApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
