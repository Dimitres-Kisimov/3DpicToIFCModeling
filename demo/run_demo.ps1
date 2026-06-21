# SCS room-population demo launcher
#   1. builds the object table + 3D scene + IFC from a scene spec
#   2. serves the repo over HTTP and opens the demo page
#
# Usage:  powershell -ExecutionPolicy Bypass -File demo\run_demo.ps1 [-Spec demo\scene_spec.json] [-Port 8000]
param(
    [string]$Spec = "demo\scene_spec.json",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # repo root (demo\ sits under it)
Set-Location $root

Write-Host "[1/3] Building object table + 3D scene from $Spec ..."
python backend\python-scripts\build_room_scene.py $Spec demo\out

Write-Host "[2/3] Building IFC/BIM file ..."
python backend\python-scripts\build_room_ifc.py demo\out

Write-Host "[2b/3] Rendering report figures (floorplan + iso) ..."
python backend\python-scripts\render_scene.py demo\out

$url = "http://localhost:$Port/demo/room_demo.html"
Write-Host "[3/3] Serving $url"
Start-Process python -ArgumentList "-m", "http.server", "$Port" -WorkingDirectory $root
Start-Sleep -Seconds 1
Start-Process $url
Write-Host "Demo open in your browser. Close the python server window to stop."
