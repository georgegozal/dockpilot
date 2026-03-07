# DockPilot

A lightweight Docker Desktop replacement built with Python + PyQt6.
Manage containers, images, volumes and networks through a clean native GUI — no Electron, no account required.
Works on **macOS** (via Colima) and **Linux** (native Docker daemon).

![DockPilot](assets/screenshot.png)

---

## Features

- **Containers** — list all containers with live status dot, ID, ports; start / stop / restart / pause / remove
- **Memory limits** — right-click any container → Set Memory Limit to cap RAM usage (e.g. `256m`, `1g`, `2g`)
- **Compose** — containers grouped by `docker-compose` project with per-group actions
- **Images** — browse, pull, remove, prune dangling images
- **Volumes** — create, inspect, remove, prune
- **Networks** — create, inspect, remove, prune
- **Logs** — streaming log viewer with search and follow mode
- **Terminal** — interactive shell inside any running container with Tab autocomplete and block cursor
- **Stats** — live CPU, memory and network sparkline graphs
- **Inspect** — JSON viewer with syntax highlighting for any resource
- **Colima lifecycle** *(macOS)* — auto-starts Colima on launch; on quit prompts to stop or keep Docker running
- **Headless mode** *(macOS)* — start or stop Colima from the terminal without opening the GUI (`-d` / `-s`)
- **Linux support** — connects directly to the Docker daemon; no Colima required

---

## Requirements

### macOS
- macOS 14+
- Python 3.10+
- [Colima](https://github.com/abiosoft/colima) — lightweight Docker VM (replaces Docker Desktop)
- Docker CLI (`brew install colima docker`)

### Linux
- Python 3.10+
- Docker Engine installed and running (`sudo apt install docker.io` or equivalent)
- Your user in the `docker` group: `sudo usermod -aG docker $USER`

---

## Setup

### Clone and install Python dependencies

```sh
git clone https://github.com/yourusername/dockpilot.git
cd dockpilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### macOS

1. Install Colima and Docker CLI:
   ```sh
   brew install colima docker
   ```
2. *(Optional)* Add the Docker socket to your shell config so the `docker` CLI works in every new terminal.

   **zsh** (default on macOS):
   ```sh
   echo 'export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"' >> ~/.zshrc && source ~/.zshrc
   ```
   **bash:**
   ```sh
   echo 'export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"' >> ~/.bashrc && source ~/.bashrc
   ```
3. Run DockPilot — it starts Colima automatically on launch. When you quit, it asks whether to stop Docker or keep it running in the background:
   ```sh
   python3 main.py
   ```

### Linux

1. Install Docker Engine (if not already installed):
   ```sh
   sudo apt install docker.io     # Debian / Ubuntu
   # or: sudo dnf install docker  # Fedora / RHEL
   ```
2. Add your user to the `docker` group (log out and back in after):
   ```sh
   sudo usermod -aG docker $USER
   ```
3. Run DockPilot — it connects to the running Docker daemon automatically:
   ```sh
   python3 main.py
   ```

---

## CLI flags

> These flags require Colima and are **macOS only**. They have no effect on Linux.

| Flag | Alias | Description |
|------|-------|-------------|
| `-d` | `--headless` | Start Colima in the background without opening the GUI |
| `-s` | `--stop` | Stop Colima from the terminal |

```sh
# Start Docker in the background (no GUI)
python3 main.py -d

# Stop Docker
python3 main.py -s

# Open the GUI normally
python3 main.py
```

---

## How it works

On macOS, Docker always needs a Linux VM to run containers. DockPilot uses **Colima** as the VM engine — it is lighter than Docker Desktop (no Electron UI, no account, ~no background services). DockPilot itself is the GUI layer on top.

```
macOS → Colima VM → dockerd → Docker SDK (Python) → DockPilot GUI
```

If Colima is not running when DockPilot opens, it starts it automatically.
When you close DockPilot, a dialog lets you choose to stop Docker or leave it running in the background.

---

## Tech stack

| Layer | Library |
|-------|---------|
| GUI | PyQt6 |
| Docker API | docker-py (Docker SDK for Python) |
| Terminal emulation | pyte |
| VM | Colima (Lima-based) |

---

## Project structure

```
dockpilot/
├── main.py                         Entry point, sets DOCKER_HOST env var
├── requirements.txt
├── assets/
│   └── screenshot.png
└── src/
    ├── app.py                      QApplication + dark theme
    ├── docker_client.py            Docker SDK wrapper (auto-detects Colima socket)
    ├── workers/
    │   ├── action_worker.py        Generic one-shot async worker + FetchWorker (non-blocking polls)
    │   ├── colima_worker.py        Colima start/stop QThread workers (macOS only)
    │   ├── logs_worker.py          Streaming log worker
    │   ├── pull_worker.py          Image pull with progress
    │   └── stats_worker.py         Live container stats
    └── ui/
        ├── main_window.py          Main window + sidebar + Colima lifecycle/quit dialog (macOS only)
        ├── containers_panel.py     Container list and actions
        ├── compose_panel.py        Docker Compose project groups
        ├── images_panel.py         Image management
        ├── volumes_panel.py        Volume management
        ├── networks_panel.py       Network management
        ├── logs_dialog.py          Streaming log viewer
        ├── terminal_widget.py      Interactive container terminal
        ├── stats_widget.py         Live stats graphs
        ├── inspect_dialog.py       JSON inspector
        └── pull_dialog.py          Pull image dialog
```

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.
