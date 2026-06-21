# SCS room-population app launcher (web app; the PySide .exe will embed this same UI).
#   starts the Flask backend and opens the browser UI.
# Usage:  powershell -ExecutionPolicy Bypass -File demo\run_app.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "Starting SCS app on http://localhost:8000/ ..."
Start-Process python -ArgumentList "backend\app_server.py" -WorkingDirectory $root
Start-Sleep -Seconds 2
Start-Process "http://localhost:8000/"
Write-Host "App open in your browser. Close the python window to stop the server."
