#!/usr/bin/env bash
# If something is wrong, run this. Reinstalls dependencies and re-registers
# the MCP server with Claude Desktop. Does not touch the database.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> Repairing Tools CRM install"
exec "$SCRIPT_DIR/install.sh"
