# Contributing to DockPilot

Thanks for improving DockPilot. This project lives at **[github.com/georgegozal/dockpilot](https://github.com/georgegozal/dockpilot)** — forks and pull requests should target upstream **`main`**.

## Before you start

- **Bug fixes and small improvements** — open a pull request and say what you tested (macOS with Colima and/or Linux with Docker Engine).
- **Large features** — open an [issue](https://github.com/georgegozal/dockpilot/issues) first so direction is clear.
- **Security** — do not post exploit details in public issues; contact the maintainer privately.

## Development setup

See [README.md — Development setup](README.md#development-setup) for clone, venv, Colima on macOS, and Docker on Linux.

Quick start:

```bash
git clone https://github.com/georgegozal/dockpilot.git
cd dockpilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Pull request workflow

1. **Fork** [georgegozal/dockpilot](https://github.com/georgegozal/dockpilot) and clone your fork.
2. Add upstream: `git remote add upstream git@github.com:georgegozal/dockpilot.git`
3. Branch from `main`, e.g. `fix/colima-socket` or `feat/compose-actions`.
4. Keep changes focused; match style in nearby files.
5. **Commit** with clear messages (see below).
6. Open a PR against **`georgegozal/dockpilot` `main`** with what changed and how you tested.

## Commit messages

Use prefixes like the existing history:

- `fix:` — bug fix  
- `feat:` — new behavior  
- `refactor:` — internal change, no user-visible change  
- `docs:` — documentation only  

## Code layout

- **`src/docker_client.py`**, **`src/workers/`** — Docker SDK and background work (minimal Qt).
- **`src/cli/`** — terminal subcommands (`dockpilot ps`, etc.).
- **`src/ui/`** — PyQt6 panels and dialogs.
- **`main.py`** — entry point, CLI flags, `DOCKER_HOST` setup.

## License

By contributing, you agree your work is licensed under **AGPL-3.0** ([LICENSE](LICENSE)).
