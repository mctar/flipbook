#!/usr/bin/env bash
# Flipbook installer for Mac/Linux.
# Idempotent: safe to run multiple times.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

step() { printf "==> %s\n" "$*"; }
note() { printf "    %s\n" "$*"; }
warn() { printf "    \033[33m%s\033[0m\n" "$*"; }

step "Flipbook installer"
note "Project root: $SCRIPT_DIR"

# --- 1. uv ----------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  step "Installing uv (Python package manager)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer drops uv into ~/.local/bin or ~/.cargo/bin; pick it up here.
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# --- 2. Dependencies ------------------------------------------------------
step "Installing dependencies"
uv sync

# --- 3. Database ----------------------------------------------------------
step "Initializing database"
uv run python -c "from app.db import init_db; init_db(); print('   Database ready.')"

# --- 4. Register MCP server with Claude Desktop --------------------------
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
MCP_SCRIPT="$SCRIPT_DIR/mcp/server.py"

case "$(uname -s)" in
  Darwin) CLAUDE_CFG_DIR="$HOME/Library/Application Support/Claude" ;;
  Linux)  CLAUDE_CFG_DIR="$HOME/.config/Claude" ;;
  *)      CLAUDE_CFG_DIR="" ;;
esac

if [ -n "$CLAUDE_CFG_DIR" ]; then
  mkdir -p "$CLAUDE_CFG_DIR"
  CLAUDE_CFG="$CLAUDE_CFG_DIR/claude_desktop_config.json"
  step "Registering MCP server"
  note "Config: $CLAUDE_CFG"
  uv run python scripts/register_mcp.py "$CLAUDE_CFG" "$PYTHON_BIN" "$MCP_SCRIPT"

  # Friendly nudge if Claude Desktop isn't installed or is currently running.
  if [ "$(uname -s)" = "Darwin" ]; then
    if [ ! -d "/Applications/Claude.app" ]; then
      warn "Claude Desktop not detected at /Applications/Claude.app."
      warn "Install from https://claude.com/download — MCP entry is written but won't load until Claude is installed."
    fi
    if pgrep -x "Claude" >/dev/null 2>&1; then
      warn "Claude Desktop is currently running. Restart it to pick up the MCP server."
    fi
  fi
else
  warn "Skipping MCP registration on this platform."
fi

# --- 5. Tailscale ---------------------------------------------------------
step "Checking Tailscale"
ts_cli=""
if command -v tailscale >/dev/null 2>&1; then
  ts_cli="$(command -v tailscale)"
elif [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]; then
  ts_cli="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi

if [ -z "$ts_cli" ]; then
  if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    note "Installing Tailscale via Homebrew…"
    brew install tailscale || warn "brew install tailscale failed; install manually from https://tailscale.com/download"
    if command -v tailscale >/dev/null 2>&1; then
      note "Start it with: brew services start tailscale"
    fi
  else
    warn "Tailscale not installed. Install from https://tailscale.com/download"
  fi
else
  note "Tailscale present: $ts_cli"
  note "If you haven't signed in yet, run: $ts_cli up"
fi

# --- 6. Power settings (Mac): stay awake when plugged in -----------------
# Without this, the laptop sleeps after idle and the phone can't reach
# Flipbook over Tailscale. Only changes the AC (charger) profile.
if [ "$(uname -s)" = "Darwin" ]; then
  step "Power settings (Mac)"
  current_ac_sleep="$(pmset -g | awk '$1 == "sleep" { print $2 }' | head -1 || true)"
  if [ "$current_ac_sleep" = "0" ]; then
    note "Already configured: idle sleep on AC = never."
  else
    note "Recommended: prevent idle sleep when plugged in (so phone can reach Flipbook)."
    note "Run when ready (requires sudo):"
    note "    sudo pmset -c sleep 0          # idle sleep on AC: never"
    note "    sudo pmset -c displaysleep 0   # display sleep on AC: never (optional)"
    note "Mac lid-close clamshell sleep cannot be disabled cleanly — keep the lid open"
    note "while charging, or attach an external display."
  fi
fi

# --- 7. Smoke test --------------------------------------------------------
step "Running doctor"
uv run python scripts/doctor.py || warn "Doctor reported issues — see above."

echo ""
step "Install complete."
note "Start the server:        ./scripts/start.sh"
note "Open the web UI:         http://localhost:8765"
note "Restart Claude Desktop to pick up the new MCP server."
