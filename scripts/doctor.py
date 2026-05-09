"""Flipbook doctor: diagnose install state and connectivity.

Cross-platform health check. Run via `scripts/doctor.bat` (Windows),
`scripts/doctor.sh` (Mac), or directly: `uv run python scripts/doctor.py`.

Each check prints OK / WARN / FAIL with a remediation hint on failure.
Exit code: 0 if everything passes (warnings are OK), 1 on any failure.

Designed for self-service triage by the end user. No prior knowledge of
the codebase required to interpret output.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

_results: list[tuple[str, str, str, str]] = []  # (status, label, detail, fix)


def _record(status: str, label: str, detail: str = "", fix: str = "") -> None:
    _results.append((status, label, detail, fix))


def _color(status: str) -> str:
    if not sys.stdout.isatty():
        return f"{status:<4}"
    palette = {
        OK:   f"\033[32m{status:<4}\033[0m",
        WARN: f"\033[33m{status:<4}\033[0m",
        FAIL: f"\033[31m{status:<4}\033[0m",
    }
    return palette.get(status, status)


# ---------- checks ----------

def check_uv() -> None:
    path = shutil.which("uv")
    if path:
        _record(OK, "uv installed", path)
    else:
        _record(FAIL, "uv installed", "not on PATH",
                "Run scripts/install (it installs uv automatically).")


def _venv_python() -> Path:
    return PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def check_venv() -> None:
    py = _venv_python()
    if py.exists():
        _record(OK, ".venv ready", str(py))
    else:
        _record(FAIL, ".venv ready", "not found",
                "Run scripts/install (or scripts/repair if .venv looks corrupted).")


def check_db() -> None:
    db = Path(os.environ.get("TOOLS_CRM_DB", str(Path.home() / ".tools-crm" / "crm.db")))
    if db.exists() and db.is_file():
        size_kb = db.stat().st_size // 1024
        _record(OK, "Database", f"{db} ({size_kb} KB)")
    else:
        _record(FAIL, "Database", f"missing at {db}",
                "Run scripts/install — it creates the database.")


def check_mcp_import() -> None:
    """Spawn Python in the venv and have it boot the MCP server in --check mode.
    Catches the most common breakage: dependency drift or path issues."""
    py = _venv_python()
    if not py.exists():
        _record(WARN, "MCP server boots", "skipped — no .venv")
        return
    server_script = PROJECT_ROOT / "mcp" / "server.py"
    try:
        result = subprocess.run(
            [str(py), str(server_script), "--check"],
            capture_output=True, text=True, timeout=15, cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and "OK" in result.stdout:
            _record(OK, "MCP server boots", "")
        else:
            tail = (result.stderr or result.stdout).strip().splitlines()
            last = tail[-1] if tail else f"exit code {result.returncode}"
            _record(FAIL, "MCP server boots", last,
                    "Run scripts/repair, then check ~/.tools-crm/mcp.log.")
    except Exception as e:
        _record(FAIL, "MCP server boots", str(e),
                "Run scripts/repair to reinstall dependencies.")


def claude_config_path() -> Path | None:
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
    if IS_MAC:
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def _claude_desktop_installed() -> bool:
    if IS_WINDOWS:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "AnthropicClaude" / "Claude.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "Claude.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Claude" / "Claude.exe",
        ]
        return any(p.exists() for p in candidates)
    if IS_MAC:
        return Path("/Applications/Claude.app").exists()
    return False


def check_claude_desktop() -> None:
    if _claude_desktop_installed():
        _record(OK, "Claude Desktop installed", "")
    else:
        _record(WARN, "Claude Desktop installed",
                "not found in default locations",
                "Install from https://claude.com/download (required for MCP usage).")


def check_mcp_registration() -> None:
    cfg = claude_config_path()
    if not cfg or not cfg.exists():
        _record(WARN, "MCP registered", "Claude config file not found",
                "Run scripts/install after Claude Desktop is installed.")
        return
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception as e:
        _record(FAIL, "MCP registered", f"config JSON is invalid ({e})",
                "Fix the file by hand or rerun scripts/install — it will replace the broken file.")
        return
    server = (data.get("mcpServers") or {}).get("tools-crm")
    if not server:
        _record(FAIL, "MCP registered", "tools-crm not in mcpServers",
                "Run scripts/install (it writes the config entry).")
        return
    cmd = server.get("command", "")
    args = server.get("args", [])
    cmd_ok = bool(cmd) and Path(cmd).exists()
    args_ok = all(Path(a).exists() for a in args if a and not a.startswith("-"))
    if cmd_ok and args_ok:
        _record(OK, "MCP registered", "tools-crm with valid paths")
    else:
        _record(FAIL, "MCP registered",
                f"registered but paths invalid (command={cmd})",
                "Run scripts/repair to refresh the paths in the config.")


def check_tailscale() -> None:
    ts = shutil.which("tailscale")
    if not ts and IS_MAC:
        # On macOS, the Tailscale GUI ships its CLI here without adding to PATH.
        candidate = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
        if candidate.exists():
            ts = str(candidate)
    if not ts:
        _record(WARN, "Tailscale installed",
                "tailscale CLI not on PATH",
                "Run scripts/install — it auto-installs Tailscale on Mac (brew) and Windows (winget).")
        return
    try:
        result = subprocess.run([ts, "status", "--json"], capture_output=True,
                                text=True, timeout=5)
        if result.returncode != 0:
            _record(WARN, "Tailscale running",
                    "status command failed (Tailscale not running?)",
                    "Open Tailscale (tray/menu bar icon) and sign in.")
            return
        data = json.loads(result.stdout)
        backend = data.get("BackendState", "?")
        self_node = data.get("Self") or {}
        host = (self_node.get("DNSName") or "").rstrip(".") or self_node.get("HostName") or "?"
        if backend == "Running":
            _record(OK, "Tailscale running", f"hostname: {host}")
        else:
            _record(WARN, "Tailscale running",
                    f"backend state: {backend}",
                    "Sign in to Tailscale via the tray/menu bar icon.")
    except Exception as e:
        _record(WARN, "Tailscale running", f"could not query: {e}", "")


def check_server_health() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as r:
            if r.status == 200:
                _record(OK, "Server responding on 8765", "")
                return
            _record(WARN, "Server responding on 8765", f"HTTP {r.status}", "")
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
        _record(WARN, "Server responding on 8765",
                "not running",
                "Start it: scripts/start (or it will auto-start at next login on Windows).")


def check_power_settings() -> None:
    """Confirm the laptop won't sleep while serving Flipbook on AC power.

    Without this, the phone can't reach the laptop over Tailscale once it
    sleeps. install.ps1 sets these on Windows; Mac is a manual sudo step.
    """
    if IS_WINDOWS:
        try:
            ps = (
                "$idle = (powercfg /getacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | "
                "Select-String 'AC Power Setting Index').ToString().Split(':')[-1].Trim();"
                "$lid  = (powercfg /getacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION | "
                "Select-String 'AC Power Setting Index').ToString().Split(':')[-1].Trim();"
                "Write-Output \"$idle|$lid\""
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10)
            out = (r.stdout or "").strip()
            idle, _, lid = out.partition("|")
            idle_int = int(idle, 16) if idle.startswith("0x") else int(idle or "-1")
            lid_int = int(lid, 16) if lid.startswith("0x") else int(lid or "-1")
            if idle_int == 0 and lid_int == 0:
                _record(OK, "Power: stays awake on AC", "idle=never, lid-close=do nothing")
            else:
                _record(WARN, "Power: stays awake on AC",
                        f"idle={idle_int}s, lid-close={lid_int}",
                        "Re-run scripts\\install.bat as Administrator (it sets these).")
        except Exception as e:
            _record(WARN, "Power: stays awake on AC", f"could not query: {e}", "")
    elif IS_MAC:
        try:
            r = subprocess.run(["pmset", "-g"], capture_output=True, text=True, timeout=5)
            ac_sleep = None
            for line in r.stdout.splitlines():
                parts = line.split()
                if parts and parts[0] == "sleep":
                    ac_sleep = parts[1]
                    break
            if ac_sleep == "0":
                _record(OK, "Power: stays awake on AC", "idle sleep on charger = never")
            else:
                _record(WARN, "Power: stays awake on AC",
                        f"idle sleep on charger = {ac_sleep or '?'} min",
                        "Run: sudo pmset -c sleep 0")
        except Exception as e:
            _record(WARN, "Power: stays awake on AC", f"could not query: {e}", "")


def check_firewall_windows() -> None:
    if not IS_WINDOWS:
        return
    try:
        ps = (
            "$f = Get-NetFirewallPortFilter -Protocol TCP | Where-Object LocalPort -eq 8765;"
            "if ($f) {"
            "  $rules = $f | ForEach-Object { Get-NetFirewallRule -AssociatedNetFirewallPortFilter $_ };"
            "  if ($rules | Where-Object { $_.Enabled -eq 'True' -and $_.Action -eq 'Allow' -and $_.Direction -eq 'Inbound' }) { 'OK' } else { 'NONE' }"
            "} else { 'NONE' }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            _record(OK, "Windows firewall allows 8765", "")
        else:
            _record(WARN, "Windows firewall allows 8765",
                    "no enabled inbound Allow rule for 8765",
                    "Run scripts/install as Administrator — it adds the rule.")
    except Exception as e:
        _record(WARN, "Windows firewall", f"could not query: {e}", "")


# ---------- driver ----------

def main() -> int:
    print("== Flipbook doctor ==")
    print(f"   Project:  {PROJECT_ROOT}")
    print(f"   Platform: {platform.system()} {platform.release()}")
    print()

    check_uv()
    check_venv()
    check_db()
    check_mcp_import()
    check_claude_desktop()
    check_mcp_registration()
    check_tailscale()
    check_server_health()
    check_firewall_windows()
    check_power_settings()

    label_w = max((len(r[1]) for r in _results), default=10) + 2
    n_fail = n_warn = 0
    for status, label, detail, fix in _results:
        print(f"   [{_color(status)}] {label:<{label_w}} {detail}")
        if fix and status != OK:
            print(f"          → {fix}")
        n_fail += (status == FAIL)
        n_warn += (status == WARN)

    print()
    if n_fail:
        print(f"== {n_fail} failure(s), {n_warn} warning(s). Fix the failures and re-run.")
        return 1
    if n_warn:
        print(f"== {n_warn} warning(s). Optional fixes above. Otherwise OK.")
        return 0
    print("== All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
