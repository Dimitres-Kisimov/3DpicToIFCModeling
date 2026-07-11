@echo off
setlocal
cd /d "%~dp0"

if not exist "node_modules" goto :not_setup
if not exist ".env" goto :not_setup
if not exist "pyenv\Scripts\python.exe" goto :not_setup

echo ================================================================
echo   3DpicToIFC is starting...
echo ================================================================
echo.
echo   Your browser will open http://localhost:3000 in a moment.
echo   KEEP THIS WINDOW OPEN - closing it stops the app.
echo   (Server log messages appear below.)
echo.

rem Open the browser a few seconds after the server starts booting.
start "" cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:3000"

node backend\server.js

echo.
echo The server has stopped. You can close this window,
echo or run start.bat again to restart the app.
pause
exit /b 0

:not_setup
echo.
echo [PROBLEM] The app is not set up yet on this computer.
echo   Please run setup.bat first (one time only), then start.bat.
echo.
pause
exit /b 1
