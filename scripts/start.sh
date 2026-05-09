#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

ts_cli=""
if command -v tailscale >/dev/null 2>&1; then
  ts_cli="$(command -v tailscale)"
elif [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]; then
  ts_cli="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi

ts_host=""
if [ -n "$ts_cli" ]; then
  ts_host="$("$ts_cli" status --json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("Self") or {}).get("DNSName","").rstrip("."))' \
    2>/dev/null || true)"
fi

echo "==> Starting Flipbook at http://localhost:8765"
if [ -n "$ts_host" ]; then
  echo "    (Phone via Tailscale: http://${ts_host}:8765)"
else
  echo "    (Tailscale not detected. Run ./scripts/install.sh to set it up.)"
fi
echo "    Press Ctrl+C to stop."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8765
