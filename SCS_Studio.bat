@echo off
title SCS Studio - photo to BIM
cd /d "%~dp0"

echo.
echo  ============================================
echo    SCS Studio  -  photo - 3D - room - BIM
echo  ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo  [!] Node.js is not installed or not on PATH.
  echo      Install it from https://nodejs.org  ^(18 or newer^), then run this again.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo  [!] Python is not installed or not on PATH.
  echo      Install it from https://python.org  ^(3.11 or newer, tick "Add to PATH"^), then run this again.
  pause
  exit /b 1
)

if not exist node_modules (
  echo  First run: installing Node packages ^(about a minute^)...
  call npm install --no-audit --no-fund
)
if not exist .pydeps_ok (
  echo  First run: installing Python packages ^(a few minutes^)...
  pip install -r requirements.txt && echo ok > .pydeps_ok
)
if not exist data\mesh_library_abo\manifest.json (
  echo.
  echo  NOTE: the ABO furniture library is not downloaded yet.
  echo  The app runs without it ^(generated catalog works^) — for the full
  echo  38-category catalog run once, in another terminal:
  echo      python backend\python-scripts\download_abo_subset.py
  echo.
)

echo  Starting the server — keep this window open while using the app.
start "" http://localhost:3000
npm start
pause
