#!/usr/bin/env bash
# DockPilot uninstaller — macOS and Linux
# Usage: bash uninstall.sh
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/dockpilot"
LAUNCHER="$HOME/.local/bin/dockpilot"
DESKTOP_FILE="$HOME/.local/share/applications/dockpilot.desktop"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[dockpilot]${NC} $*"; }
error() { echo -e "${RED}[dockpilot] ERROR:${NC} $*" >&2; exit 1; }

[[ -d "$INSTALL_DIR" ]] || error "DockPilot does not appear to be installed (expected $INSTALL_DIR)."

read -r -p "Remove DockPilot from $INSTALL_DIR? [y/N] " confirm
[[ "${confirm,,}" == "y" ]] || { echo "Aborted."; exit 0; }

rm -rf "$INSTALL_DIR"
info "Removed $INSTALL_DIR"

[[ -f "$LAUNCHER" ]] && { rm -f "$LAUNCHER"; info "Removed $LAUNCHER"; }
[[ -f "$DESKTOP_FILE" ]] && {
  rm -f "$DESKTOP_FILE"
  info "Removed $DESKTOP_FILE"
  command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
}

info "DockPilot uninstalled."
