"""make_release_zip.py — build the downloadable SCS Studio app bundle.

Contains everything needed to RUN the app on a fresh Windows machine:
code, the full catalog (ABO + generated + variants), the 15-building fleet,
galleries, docs. Excludes: node_modules (npm install), runtime outputs,
caches, and the 7.5 GB benchmark result meshes (noted in the bundle README).

    python scripts/make_release_zip.py
Out: deliverable/local_only/SCS_Studio_App_v1.0.zip  (NOT for GitHub)
"""
import os
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys
LITE = "--lite" in sys.argv
OUT = REPO / "deliverable" / "local_only" / (
    "SCS_Studio_App_v2.0_lite.zip" if LITE else "SCS_Studio_App_v2.0.zip")

ABO = "data/mesh_library_abo"
INCLUDE = [
    "backend", "frontend", "scripts", "docs", "legacy",
    "data/generated_assets", "data/buildings",
    "data/mesh_library_polyhaven", "data/mesh_library", "data/furniture_library",
    "data/demo_photos", "sample_buildings", "demo",
    "deliverable/cloud_gallery", "deliverable/manuals",
    "package.json", "package-lock.json", "requirements.txt", "SCS_Studio.bat",
    "README.md", "CREDITS.md", "LICENSE",
]
EXCLUDE_DIRS = {"node_modules", "__pycache__", ".git", "_ingest_work",
                "_listings_work", "app_out", "outputs", "engines"}
EXCLUDE_EXT = {".pyc"}

BUNDLE_README = """SCS Studio — photo -> 3D -> room -> BIM  (app bundle v1.0)
=============================================================

RUN ON WINDOWS — EASIEST: double-click  SCS_Studio.bat
  It checks Node/Python, installs packages on first run, starts the server
  and opens http://localhost:3000 in your browser. Keep its window open.

  Manual alternative:
  1. Install Node.js 18+ and Python 3.11+ (python on PATH).
  2. In this folder:   npm install
  3. Python deps:      pip install -r requirements.txt
  4. Start:            npm start
  5. Open:             http://localhost:3000
     (3D needs Chrome with "Use graphics acceleration" ON.)

FIRST-RUN NOTES
  - The first photo->3D generation downloads the TripoSR weights once
    (internet required once; cached afterwards).
  - A building's first populate performs a one-time geometry scan
    (minutes for big IFCs; instant afterwards).
  - demo/app_out and outputs/ are created automatically at runtime.

ABO FURNITURE LIBRARY (lite bundle only)
  The lite bundle ships without the 4.7 GB ABO mesh library (a public
  Amazon dataset, CC-BY-4.0). Rebuild it once before first use:
      python backend/python-scripts/download_abo_subset.py
  (internet required once; ~30-60 min depending on connection)

NOT INCLUDED (size)
  - benchmark result meshes (7.5 GB) — the research-hub benchmark pages
    list stats but their 3D variants need that folder; available separately.
  - 3D engine installs (TRELLIS/TripoSG/...) — installable from inside the
    app on machines that meet the requirements (see Engine Manuals).

LICENSES: MIT (code); catalog meshes ABO CC-BY-4.0, PolyHaven CC0,
generated/parametric items project-owned. See CREDITS.md.
"""


def want(path: Path) -> bool:
    parts = set(p.name for p in path.parents) | {path.name}
    if parts & EXCLUDE_DIRS:
        return False
    if path.suffix.lower() in EXCLUDE_EXT:
        return False
    return True


def main():
    t0 = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr("SCS_Studio/README_FIRST.txt", BUNDLE_README)
        z.writestr("SCS_Studio/demo/app_out/.keep", "")
        z.writestr("SCS_Studio/outputs/.keep", "")
        for inc in (INCLUDE if LITE else INCLUDE + [ABO]):
            p = REPO / inc
            if p.is_file():
                z.write(p, f"SCS_Studio/{inc}")
                n += 1
                continue
            for f in p.rglob("*"):
                if f.is_file() and want(f):
                    z.write(f, f"SCS_Studio/{f.relative_to(REPO).as_posix()}")
                    n += 1
                    if n % 500 == 0:
                        print(f"  {n} files...", flush=True)
    mb = OUT.stat().st_size / 1e6
    print(f"bundle: {n} files, {mb:.0f} MB -> {OUT}  ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
