#!/usr/bin/env bash
# DockPilot installer / updater -- macOS and Linux
# Usage: bash install.sh
set -euo pipefail

REPO_URL="https://github.com/georgegozal/dockpilot.git"
INSTALL_DIR="$HOME/.local/share/dockpilot"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/dockpilot"
DESKTOP_FILE="$HOME/.local/share/applications/dockpilot.desktop"
ICON_SRC="$INSTALL_DIR/assets/icon.png"

# -- Colour helpers -----------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[dockpilot]${NC} $*"; }
warn()  { echo -e "${YELLOW}[dockpilot]${NC} $*"; }
error() { echo -e "${RED}[dockpilot] ERROR:${NC} $*" >&2; exit 1; }

# -- Platform detection -------------------------------------------------------
PLATFORM=""
case "$(uname -s)" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      error "Unsupported OS: $(uname -s)" ;;
esac

# -- Detect if running from inside a cloned repo ------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/main.py" && -f "$SCRIPT_DIR/requirements.txt" ]]; then
  _IN_REPO=true
else
  _IN_REPO=false
fi

info "Installing DockPilot on ${PLATFORM}..."

# -- Python check -------------------------------------------------------------
PYTHON=""
for py in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$py" &>/dev/null; then
    if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PYTHON="$py"
      break
    fi
  fi
done
[[ -z "$PYTHON" ]] && error "Python 3.10+ is required. Install it and re-run."
info "Using $("${PYTHON}" --version)"

# -- Copy or clone source to INSTALL_DIR --------------------------------------
mkdir -p "$INSTALL_DIR"

if [[ "$_IN_REPO" == true ]]; then
  info "Syncing source to ${INSTALL_DIR} ..."
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/"
elif [[ -d "$INSTALL_DIR/.git" ]]; then
  command -v git &>/dev/null || error "git is required. Install it and re-run."
  info "Updating existing installation..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  command -v git &>/dev/null || error "git is required. Install it and re-run."
  info "Cloning DockPilot to ${INSTALL_DIR} ..."
  git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi

# -- Python virtual environment -----------------------------------------------
VENV="$INSTALL_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
  info "Creating virtual environment..."
  "$PYTHON" -m venv "$VENV"
fi

info "Installing Python dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# -- Shell launcher -----------------------------------------------------------
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
exec "$VENV/bin/python3" "$INSTALL_DIR/main.py" "\$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"
info "Shell launcher: ${LAUNCHER}"

# -- Linux: .desktop file -----------------------------------------------------
if [[ "$PLATFORM" == "linux" ]]; then
  mkdir -p "$(dirname "$DESKTOP_FILE")"

  if [[ -f "$ICON_SRC" ]]; then
    ICON_VALUE="$ICON_SRC"
  else
    ICON_VALUE="utilities-terminal"
  fi

  cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DockPilot
Comment=Lightweight Docker Desktop replacement
Exec=$LAUNCHER %u
Icon=$ICON_VALUE
Terminal=false
Categories=System;
Keywords=docker;container;
DESKTOP_EOF

  command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

  info ".desktop file: ${DESKTOP_FILE}"
fi

# -- macOS: PATH + DOCKER_HOST + .app bundle ----------------------------------
if [[ "$PLATFORM" == "macos" ]]; then
  _detect_shell_rc() {
    case "$(basename "${SHELL:-bash}")" in
      zsh)  echo "$HOME/.zshrc" ;;
      bash) echo "$HOME/.bashrc" ;;
      fish) echo "$HOME/.config/fish/config.fish" ;;
      *)    echo "$HOME/.profile" ;;
    esac
  }
  SHELL_RC="$(_detect_shell_rc)"

  if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    PATH_LINE="export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    warn "$BIN_DIR is not in your PATH."
    read -r -p "    Add it to $SHELL_RC automatically? [Y/n] " yn
    if [[ "$yn" != [Nn]* ]]; then
      echo "" >> "$SHELL_RC"
      echo "# Added by DockPilot installer" >> "$SHELL_RC"
      echo "$PATH_LINE" >> "$SHELL_RC"
      info "Added PATH entry to ${SHELL_RC}"
      export PATH="$BIN_DIR:$PATH"
    else
      warn "Skipped. Add this to your shell config manually:"
      warn "  $PATH_LINE"
    fi
  fi

  COLIMA_SOCK="\${HOME}/.colima/default/docker.sock"
  DOCKER_HOST_LINE="export DOCKER_HOST=\"unix://$COLIMA_SOCK\""

  if ! grep -qF "DOCKER_HOST" "${SHELL_RC}" 2>/dev/null; then
    echo ""
    info "Colima uses a custom Docker socket. Without DOCKER_HOST set,"
    info "the 'docker' CLI won't work in new terminals."
    read -r -p "    Add DOCKER_HOST to $SHELL_RC automatically? [Y/n] " yn
    if [[ "$yn" != [Nn]* ]]; then
      echo "" >> "$SHELL_RC"
      echo "# Colima Docker socket -- added by DockPilot installer" >> "$SHELL_RC"
      echo "$DOCKER_HOST_LINE" >> "$SHELL_RC"
      info "Added DOCKER_HOST to ${SHELL_RC}"
    else
      warn "Skipped. Add this line manually if you want 'docker' CLI to work:"
      warn "  $DOCKER_HOST_LINE"
    fi
  else
    info "DOCKER_HOST already set in ${SHELL_RC} -- skipping."
  fi

  APP_BUNDLE="/Applications/DockPilot.app"
  info "Creating ${APP_BUNDLE} ..."
  mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

  cat > "$APP_BUNDLE/Contents/MacOS/dockpilot" << APP_EOF
#!/bin/bash
exec "$VENV/bin/python3" "$INSTALL_DIR/main.py"
APP_EOF
  chmod +x "$APP_BUNDLE/Contents/MacOS/dockpilot"

  cat > "$APP_BUNDLE/Contents/Info.plist" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>DockPilot</string>
    <key>CFBundleDisplayName</key>
    <string>DockPilot</string>
    <key>CFBundleIdentifier</key>
    <string>com.keytype.dockpilot</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>dockpilot</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
</dict>
</plist>
PLIST_EOF

  xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true
  info ".app bundle: ${APP_BUNDLE}"
fi

# -- Done ---------------------------------------------------------------------
echo ""
info "DockPilot installed successfully!"
info "Source lives at: ${INSTALL_DIR}"
info "Run from terminal: dockpilot"
if [[ "$PLATFORM" == "macos" ]]; then
  info "Or open from Applications / Dock / Spotlight."
  info "(Re-run install.sh at any time to update.)"
fi
