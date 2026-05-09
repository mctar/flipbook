"""Register the tools-crm MCP server in claude_desktop_config.json.

Reads the existing config (if any), inserts or updates our entry, writes
it back. Never clobbers other MCP servers the user has configured.

Usage: register_mcp.py <config_path> <python_bin> <mcp_script>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: register_mcp.py <config_path> <python_bin> <mcp_script>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[1])
    python_bin = sys.argv[2]
    mcp_script = sys.argv[3]

    config: dict = {}
    if config_path.exists() and config_path.stat().st_size > 0:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"WARNING: existing config at {config_path} is not valid JSON ({e}).", file=sys.stderr)
            backup = config_path.with_suffix(config_path.suffix + ".broken")
            backup.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"         Backed up to {backup} and starting fresh.", file=sys.stderr)
            config = {}

    config.setdefault("mcpServers", {})
    config["mcpServers"]["tools-crm"] = {
        "command": python_bin,
        "args": [mcp_script],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"   Registered 'tools-crm' MCP server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
