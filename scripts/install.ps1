# Flipbook installer for Windows.
# Idempotent: safe to run multiple times.
# Should be invoked via install.bat, which self-elevates so the firewall step works.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Note($msg) { Write-Host "    $msg" }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Test-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    return ([System.Security.Principal.WindowsPrincipal]::new($id)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Step "Flipbook installer"
Write-Note "Project root: $ProjectRoot"
$IsAdmin = Test-Admin
if (-not $IsAdmin) {
    Write-Warn "Not running as Administrator — firewall rule will be skipped."
    Write-Warn "Re-run scripts\install.bat to elevate (it self-elevates by default)."
}

# --- 1. uv ----------------------------------------------------------------
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Step "Installing uv (Python package manager)"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    # Pick up uv in this session
    $env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;" + $env:Path
}

# --- 2. Dependencies ------------------------------------------------------
Write-Step "Installing dependencies"
uv sync

# --- 3. Database ----------------------------------------------------------
Write-Step "Initializing database"
uv run python -c "from app.db import init_db; init_db(); print('   Database ready.')"

# --- 4. Register MCP server with Claude Desktop --------------------------
$PythonBin = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$McpScript = Join-Path $ProjectRoot "mcp\server.py"
$ClaudeCfgDir = Join-Path $env:APPDATA "Claude"
$ClaudeCfg = Join-Path $ClaudeCfgDir "claude_desktop_config.json"

if (-not (Test-Path $ClaudeCfgDir)) {
    New-Item -ItemType Directory -Path $ClaudeCfgDir | Out-Null
}

Write-Step "Registering MCP server"
Write-Note "Config: $ClaudeCfg"
uv run python scripts\register_mcp.py $ClaudeCfg $PythonBin $McpScript

# Detect Claude Desktop and warn if missing
$claudePaths = @(
    "$env:LOCALAPPDATA\AnthropicClaude\Claude.exe",
    "$env:LOCALAPPDATA\Programs\claude\Claude.exe",
    "$env:PROGRAMFILES\Claude\Claude.exe"
)
$claudeFound = $claudePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $claudeFound) {
    Write-Warn "Claude Desktop not detected. Install it from https://claude.com/download"
    Write-Warn "and run this installer again — the MCP entry has been written but won't load until Claude is installed."
} else {
    Write-Note "Claude Desktop found: $claudeFound"
    # If Claude is currently running, the MCP config won't reload until restart
    $running = Get-Process -Name "Claude" -ErrorAction SilentlyContinue
    if ($running) {
        Write-Warn "Claude Desktop is currently running. Restart it to pick up the MCP server."
    }
}

# --- 5. Tailscale ---------------------------------------------------------
Write-Step "Checking Tailscale"
$tsCmd = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $tsCmd) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Note "Installing Tailscale via winget…"
        try {
            winget install --id Tailscale.Tailscale -e --silent --accept-source-agreements --accept-package-agreements
            # Re-resolve PATH to pick up the new install
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $tsCmd = Get-Command tailscale -ErrorAction SilentlyContinue
        } catch {
            Write-Warn "winget install failed: $_"
            Write-Warn "Install Tailscale manually from https://tailscale.com/download"
        }
    } else {
        Write-Warn "winget not available. Install Tailscale manually from https://tailscale.com/download"
    }
}
if ($tsCmd) {
    Write-Note "Tailscale present: $($tsCmd.Source)"
    Write-Note "If you haven't signed in yet, click the Tailscale tray icon and log in."
}

# --- 6. Windows firewall: allow inbound 8765 ------------------------------
Write-Step "Configuring firewall for port 8765"
if (-not $IsAdmin) {
    Write-Warn "Skipping firewall rule — not Administrator. Phone-via-Tailscale may be blocked."
    Write-Warn "Re-run scripts\install.bat (it self-elevates) to add the rule."
} else {
    $ruleName = "Flipbook (port 8765)"
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Note "Firewall rule already present."
    } else {
        try {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound `
                -LocalPort 8765 -Protocol TCP -Action Allow `
                -Profile Private,Domain -ErrorAction Stop | Out-Null
            Write-Note "Added firewall rule: inbound 8765/tcp (Private + Domain)."
        } catch {
            Write-Warn "Could not add firewall rule: $_"
        }
    }
}

# --- 7. Power settings: stay awake when plugged in -----------------------
# Without this, the laptop sleeps after idle / lid close and the phone can't
# reach Flipbook over Tailscale. We only change the AC profile — battery
# behaviour stays default so the laptop still sleeps when unplugged.
Write-Step "Configuring power: stay awake while plugged in"
try {
    powercfg /change standby-timeout-ac 0      | Out-Null  # idle sleep on AC: never
    powercfg /change hibernate-timeout-ac 0    | Out-Null  # idle hibernate on AC: never
    powercfg /change monitor-timeout-ac 0      | Out-Null  # screen-off on AC: never (so phone-served pages don't time out either)
    # SUB_BUTTONS \ LIDACTION = 0 (do nothing on lid close while plugged in)
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0 | Out-Null
    powercfg /setactive SCHEME_CURRENT | Out-Null
    Write-Note "AC profile: never sleep, never hibernate, lid-close = do nothing."
    Write-Note "Battery profile is unchanged (laptop still sleeps when unplugged)."
} catch {
    Write-Warn "Could not change power settings: $_"
}

# --- 8. Auto-start at login -----------------------------------------------
Write-Step "Configuring auto-start at login"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcut = Join-Path $startupDir "Flipbook.lnk"
$silentVbs = Join-Path $ProjectRoot "scripts\start_silent.vbs"
try {
    $wshShell = New-Object -ComObject WScript.Shell
    $lnk = $wshShell.CreateShortcut($shortcut)
    $lnk.TargetPath = "wscript.exe"
    $lnk.Arguments = "`"$silentVbs`""
    $lnk.WorkingDirectory = $ProjectRoot
    $lnk.Description = "Start Flipbook in the background"
    $lnk.Save()
    Write-Note "Startup shortcut: $shortcut"
} catch {
    Write-Warn "Could not create Startup shortcut: $_"
}

# --- 9. Smoke test --------------------------------------------------------
Write-Step "Running doctor"
uv run python scripts\doctor.py
$doctorExit = $LASTEXITCODE

Write-Host ""
Write-Step "Install complete."
if ($doctorExit -ne 0) {
    Write-Warn "Doctor reported failures — see above. Fix and re-run scripts\repair.bat."
} else {
    Write-Note "Start the server now:    scripts\start.bat"
    Write-Note "Open the web UI:         http://localhost:8765"
    Write-Note "Server will also auto-start on next login."
    Write-Note "Restart Claude Desktop to pick up the MCP server."
}
