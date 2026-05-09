@echo off
REM Flipbook installer for Windows.
REM Self-elevates to Administrator so the firewall rule (port 8765) can be added.
REM A single UAC prompt at install time pays for trouble-free phone access later.
setlocal
set "SCRIPT_DIR=%~dp0"

REM Detect admin: `net session` only succeeds when elevated.
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator privileges (one-time, for the firewall rule)...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1"
echo.
echo Press any key to close this window.
pause >nul
endlocal
