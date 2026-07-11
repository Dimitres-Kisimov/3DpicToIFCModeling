# ============================================================================
# build_release.ps1 - assemble the Stage A "GitHub Release zip" bundle.
#
# Windows PowerShell 5.1 compatible (no &&, no ternary, no ?? operators).
#
# What it does:
#   1. Copies the runtime pieces of the app (backend/, frontend/, package.json,
#      package-lock.json, sample_buildings/, licenses, and the release/ install
#      scripts) into  release\dist\3DpicToIFC-v<Version>\
#   2. Builds a STARTER CATALOG: manifest.json + index.faiss + all thumbnails
#      from data\mesh_library_abo, plus only a small, size-budgeted subset of
#      the .glb meshes (the full ABO library is ~4.8 GB / 982 GLBs - far too
#      big for a release zip). Missing GLBs degrade gracefully: the room
#      builder lists only meshes that exist, and photo-retrieval falls back to
#      procedural primitives.
#   3. Zips the bundle to  release\dist\3DpicToIFC-StageA.zip  and prints the
#      final size.
#
# Explicitly EXCLUDED from the bundle:
#   .git, node_modules (npm ci at install time), benchmark\, deliverable\,
#   docs\, models\ (822 MB of local weights - SAM2/CLIP fall back gracefully;
#   setup.bat optionally re-downloads the SAM2 checkpoint), __pycache__,
#   *.pyc, root-level test *.glb files, outputs\, uploads\, temp\, data\
#   above the starter subset, and the developer .env (setup.bat writes a
#   fresh one pointing at the local pyenv).
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File release\build_release.ps1
#   powershell -File release\build_release.ps1 -CatalogPerCategory 3 -CatalogMaxTotalMB 300
# ============================================================================

[CmdletBinding()]
param(
    # Version tag used in the bundle folder name.
    [string]$Version = "0.9.0-stageA",

    # Source of the furniture catalog. Parameterized so a different / trimmed
    # library can be swapped in without editing the script.
    [string]$CatalogSource = "",

    # How many GLB meshes to ship per furniture category (smallest first).
    [int]$CatalogPerCategory = 2,

    # Hard budget for the starter catalog meshes, in MB. If the per-category
    # pick overshoots this, the largest meshes are dropped until it fits.
    [int]$CatalogMaxTotalMB = 200
)

$ErrorActionPreference = "Stop"

# --- paths ------------------------------------------------------------------
$ReleaseDir = $PSScriptRoot
$RepoRoot   = Split-Path -Parent $ReleaseDir
if ($CatalogSource -eq "") {
    $CatalogSource = Join-Path $RepoRoot "data\mesh_library_abo"
}

$DistDir    = Join-Path $ReleaseDir "dist"
$BundleName = "3DpicToIFC-v$Version"
$Bundle     = Join-Path $DistDir $BundleName
$ZipPath    = Join-Path $DistDir "3DpicToIFC-StageA.zip"

Write-Host "Repo root      : $RepoRoot"
Write-Host "Bundle folder  : $Bundle"
Write-Host "Catalog source : $CatalogSource"
Write-Host ""

# --- clean slate --------------------------------------------------------------
if (Test-Path $Bundle) {
    Write-Host "Removing previous bundle folder..."
    Remove-Item -Recurse -Force $Bundle
}
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null

# --- helper: recursive copy that prunes python bytecode ----------------------
function Copy-Tree {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path $Source)) {
        Write-Warning "SKIP (missing): $Source"
        return
    }
    Copy-Item -Path $Source -Destination $Destination -Recurse -Force
    # prune bytecode caches from whatever was just copied
    $copied = Join-Path $Destination (Split-Path -Leaf $Source)
    if (Test-Path $copied) {
        Get-ChildItem -Path $copied -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force
        Get-ChildItem -Path $copied -Recurse -File -Include "*.pyc", "*.pyo" -ErrorAction SilentlyContinue |
            Remove-Item -Force
    }
}

# --- 1. app code --------------------------------------------------------------
Write-Host "Copying backend/ (includes backend\python-scripts and the vendored TripoSR package)..."
Copy-Tree -Source (Join-Path $RepoRoot "backend") -Destination $Bundle
# README illustrations from the vendored TripoSR repo (~23 MB) are not runtime files.
# NOTE: backend\triposr\examples IS runtime - server.js serves it at /sample.
$figuresDir = Join-Path $Bundle "backend\triposr\figures"
if (Test-Path $figuresDir) { Remove-Item -Recurse -Force $figuresDir }

Write-Host "Copying frontend/ ..."
Copy-Tree -Source (Join-Path $RepoRoot "frontend") -Destination $Bundle

Write-Host "Copying package manifests and attribution files..."
Copy-Item (Join-Path $RepoRoot "package.json")      $Bundle
Copy-Item (Join-Path $RepoRoot "package-lock.json") $Bundle
if (Test-Path (Join-Path $RepoRoot ".env.example")) { Copy-Item (Join-Path $RepoRoot ".env.example") $Bundle }
if (Test-Path (Join-Path $RepoRoot "CREDITS.md"))   { Copy-Item (Join-Path $RepoRoot "CREDITS.md")   $Bundle }
Copy-Tree -Source (Join-Path $RepoRoot "licenses") -Destination $Bundle

Write-Host "Copying sample_buildings/ (Duplex demo IFC for the building-population feature)..."
Copy-Tree -Source (Join-Path $RepoRoot "sample_buildings") -Destination $Bundle

# --- 2. starter catalog --------------------------------------------------------
Write-Host ""
Write-Host "Building starter catalog subset..."

$CatDest = Join-Path $Bundle "data\mesh_library_abo"
New-Item -ItemType Directory -Force -Path $CatDest | Out-Null

if (Test-Path $CatalogSource) {
    # index + manifest are small and REQUIRED for retrieval + room builder
    foreach ($f in @("manifest.json", "index.faiss")) {
        $src = Join-Path $CatalogSource $f
        if (Test-Path $src) { Copy-Item $src $CatDest }
    }
    # all thumbnails (~2 MB total) so the catalog browser looks complete
    Get-ChildItem -Path $CatalogSource -Filter "*.thumb.png" -File |
        Copy-Item -Destination $CatDest

    # pick GLBs: group by category prefix (file names are <category>_<ASIN>.glb),
    # take the N smallest per category, then enforce the total MB budget.
    $glbs = Get-ChildItem -Path $CatalogSource -Filter "*.glb" -File
    $groups = @{}
    foreach ($g in $glbs) {
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($g.Name)
        $cat  = $stem -replace "_[A-Za-z0-9]+$", ""
        if (-not $groups.ContainsKey($cat)) { $groups[$cat] = New-Object System.Collections.ArrayList }
        [void]$groups[$cat].Add($g)
    }

    $selected = New-Object System.Collections.ArrayList
    foreach ($cat in ($groups.Keys | Sort-Object)) {
        $take = $groups[$cat] | Sort-Object Length | Select-Object -First $CatalogPerCategory
        foreach ($t in $take) { [void]$selected.Add($t) }
    }

    # hand-picked "known clean" meshes the app prefers - always include if present
    $alwaysInclude = @("bookshelf_B07PPNNCM2.glb")
    foreach ($name in $alwaysInclude) {
        $src = Join-Path $CatalogSource $name
        $already = $selected | Where-Object { $_.Name -eq $name }
        if ((Test-Path $src) -and (-not $already)) {
            [void]$selected.Add((Get-Item $src))
        }
    }

    # enforce total budget by dropping the largest picks first
    $sumBytes = ($selected | Measure-Object -Property Length -Sum).Sum
    $budget   = $CatalogMaxTotalMB * 1MB
    if ($sumBytes -gt $budget) {
        Write-Host ("  Catalog pick is {0:N0} MB - trimming to {1} MB budget..." -f ($sumBytes / 1MB), $CatalogMaxTotalMB)
        $ordered = $selected | Sort-Object Length -Descending
        foreach ($big in $ordered) {
            if ($sumBytes -le $budget) { break }
            $selected.Remove($big)
            $sumBytes = $sumBytes - $big.Length
        }
    }

    foreach ($g in $selected) {
        Copy-Item $g.FullName $CatDest
        # matching preview render, if one exists (optional nicety)
        $preview = Join-Path $CatalogSource ($g.BaseName + ".preview.png")
        if (Test-Path $preview) { Copy-Item $preview $CatDest }
    }
    $shippedMB = ($selected | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host ("  Starter catalog: {0} meshes, {1:N0} MB (of {2} available)" -f $selected.Count, $shippedMB, $glbs.Count)
} else {
    Write-Warning "Catalog source not found: $CatalogSource - bundle will use procedural primitives only."
}

# procedural fallback library (tiny) - used when no ABO mesh matches
Copy-Tree -Source (Join-Path $RepoRoot "data\mesh_library") -Destination (Join-Path $Bundle "data")

# empty runtime directories (server also auto-creates most of these on boot).
# Compress-Archive silently drops EMPTY folders, so each gets a placeholder file.
foreach ($d in @("data\generated_assets", "data\buildings", "outputs", "uploads", "temp", "demo\app_out", "models")) {
    $dir = Join-Path $Bundle $d
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Set-Content -Path (Join-Path $dir "_placeholder.txt") -Value "Runtime folder used by the app. Safe to ignore." -Encoding ASCII
}

# --- 3. installer files --------------------------------------------------------
Write-Host ""
Write-Host "Copying installer files from release/ ..."
foreach ($f in @("setup.bat", "start.bat", "requirements-app.txt", "INSTALL.md", "RELEASE_NOTES_STAGE_A.md")) {
    $src = Join-Path $ReleaseDir $f
    if (Test-Path $src) {
        Copy-Item $src $Bundle
    } else {
        Write-Warning "Missing installer file: $src"
    }
}

# --- 4. zip --------------------------------------------------------------------
Write-Host ""
Write-Host "Compressing to $ZipPath (this can take a few minutes)..."
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $Bundle -DestinationPath $ZipPath -CompressionLevel Optimal

$bundleBytes = (Get-ChildItem -Path $Bundle -Recurse -File | Measure-Object -Property Length -Sum).Sum
$zipItem = Get-Item $ZipPath
Write-Host ""
Write-Host "================================================================"
Write-Host ("Bundle folder : {0}  ({1:N0} MB uncompressed)" -f $Bundle, ($bundleBytes / 1MB))
Write-Host ("Release zip   : {0}" -f $ZipPath)
Write-Host ("Zip size      : {0:N1} MB" -f ($zipItem.Length / 1MB))
Write-Host "================================================================"
