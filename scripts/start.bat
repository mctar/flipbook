@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo ==^> Starting Flipbook at http://localhost:8765

REM Resolve the actual Tailscale MagicDNS hostname (not just %COMPUTERNAME%)
set "TS_HOST="
where tailscale >nul 2>&1
if not errorlevel 1 (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { ((tailscale status --json | ConvertFrom-Json).Self.DNSName).TrimEnd('.') } catch { '' }"`) do (
        set "TS_HOST=%%i"
    )
)
if defined TS_HOST (
    echo     ^(Phone via Tailscale: http://%TS_HOST%:8765^)
) else (
    echo     ^(Tailscale not detected. Run scripts\install.bat to set it up.^)
)
echo     Press Ctrl+C to stop.
start "" http://localhost:8765
uv run uvicorn app.main:app --host 0.0.0.0 --port 8765
endlocal
