@echo off
REM Launch TradingView Desktop with Chrome DevTools Protocol enabled on port 9222
REM MSIX apps don't inherit env vars from shell, so we launch the EXE directly with the flag

REM Kill existing TradingView instances
taskkill /F /IM TradingView.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Starting TradingView Desktop with CDP on port 9222...
start "" "C:\Program Files\WindowsApps\TradingView.Desktop_3.0.0.7652_x64__n534cwy3pjxzj\TradingView.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\babco\AppData\Roaming\TradingView"

echo Waiting for CDP to become available...
timeout /t 5 /nobreak >nul

:check
curl -s http://localhost:9222/json/version >nul 2>&1
if %errorlevel% neq 0 (
    echo Still waiting...
    timeout /t 2 /nobreak >nul
    goto check
)

echo.
echo CDP is ready on http://localhost:9222
curl -s http://localhost:9222/json/version
echo.
echo TradingView is running with remote debugging enabled.
