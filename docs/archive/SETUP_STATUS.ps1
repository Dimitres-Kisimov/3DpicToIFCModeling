#!/usr/bin/env powershell
<#
Installation Setup Script - Summary and Test
#>

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Installation Status - 3D to IFC Modeling Project" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

# Node.js & npm
Write-Host "`n✓ Node.js:" -ForegroundColor Green
node --version
Write-Host "✓ npm:" -ForegroundColor Green
npm --version

# Check node_modules
Write-Host "`n✓ npm packages installed:" -ForegroundColor Green
$count = (Get-ChildItem "node_modules" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "$count packages" -ForegroundColor Yellow

# Python setup
Write-Host "`n✓ Python (system):" -ForegroundColor Green
python --version

Write-Host "✓ Python venv:" -ForegroundColor Green
if (Test-Path ".\venv\Scripts\python.exe") {
    Write-Host "✓ Virtual environment ready" -ForegroundColor Yellow
    .\venv\Scripts\python.exe --version
}

# Show installed Python packages
Write-Host "`n✓ Python packages (in venv):" -ForegroundColor Green
& .\venv\Scripts\pip.exe list 2>$null | Select-Object -First 20

# Configuration
Write-Host "`n✓ Configuration files:" -ForegroundColor Green
if (Test-Path ".env") { 
    Write-Host "  ✓ .env created" -ForegroundColor Yellow 
}
if (Test-Path ".gitignore") { 
    Write-Host "  ✓ .gitignore exists" -ForegroundColor Yellow 
}

# Project structure
Write-Host "`n✓ Project directories:" -ForegroundColor Green
$dirs = @("backend", "frontend", "docs", "temp", "venv")
foreach ($dir in $dirs) {
    if (Test-Path $dir) {
        Write-Host "  ✓ $dir" -ForegroundColor Yellow
    }
}

Write-Host "`n==============================================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "
1. Complete Python dependencies installation:
   .\venv\Scripts\pip.exe install -r requirements.txt

2. Start the development server:
   npm run dev

3. Open http://localhost:3000 in your browser

4. Click 'Check Health' button to verify Python environment
" -ForegroundColor White
