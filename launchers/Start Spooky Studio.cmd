@echo off
rem Double-click to start Spooky Studio on the Pi and open it in your browser.
rem If spooky-pi.local doesn't work on your network, put the Pi's address here instead (e.g. 10.0.3.68).
set PI_HOST=spooky-pi.local
set PI_USER=spooky-pi

title Spooky Studio
echo.
echo   Starting Spooky Studio on the Pi...
echo   (If it asks for a password, type the Pi password and press Enter.
echo    The letters won't show while you type - that's normal.)
echo.
ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 %PI_USER%@%PI_HOST% "bash ~/spooky/scripts/studio-ctl.sh start"
if errorlevel 1 goto failed

start "" "http://%PI_HOST%:8080"
echo.
echo   Spooky Studio is open in your browser. You can close this window.
ping -n 6 127.0.0.1 >nul
exit /b 0

:failed
echo.
echo   Couldn't start Spooky Studio. Check that the Pi is switched on and on the same network,
echo   then try again. If it keeps failing, send a photo of this window to the project team.
echo.
pause
exit /b 1
