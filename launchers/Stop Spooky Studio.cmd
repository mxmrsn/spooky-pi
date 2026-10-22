@echo off
rem Double-click to stop Spooky Studio on the Pi (e.g. before running the real show).
set PI_HOST=spooky-pi.local
set PI_USER=spooky-pi

title Spooky Studio
echo.
echo   Stopping Spooky Studio on the Pi...
echo.
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 %PI_USER%@%PI_HOST% "bash ~/spooky/scripts/studio-ctl.sh stop"
if errorlevel 1 (
  echo.
  echo   Couldn't reach the Pi. Check that it's switched on and on the same network.
  echo.
  pause
  exit /b 1
)
ping -n 4 127.0.0.1 >nul
