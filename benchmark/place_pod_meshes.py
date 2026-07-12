"""place_pod_meshes.py — fast visualizer drop for pod results (no IFC gate).

Copies out170/<engine>/listNN_<category>.glb -> results/listNN/<category>/<engine>.glb
so build_candidates.py picks every engine up as an emblem-badged candidate next
to TripoSR raw/improved. The slow IFC-gated catalog ingestion (ingest_pod_results.py)
runs separately — this script exists so the comparison pages are viewable minutes
after a download, not hours.

    python place_pod_meshes.py <extracted_results_root>
"""
from __future__ import annotations
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
KEY = re.compile(r"^(list\d+)_(.+)$")

root = Path(sys.argv[1]).resolve()
placed = 0
engines = set()
for glb in sorted((root / "out170").glob("*/*.glb")):
    m = KEY.match(glb.stem)
    if not m:
        continue
    engine = glb.parent.name
    dest = RES / m.group(1) / m.group(2) / f"{engine}.glb"
    if not dest.parent.is_dir():
        continue                     # category folder unknown locally — skip
    shutil.copy2(glb, dest)
    engines.add(engine)
    placed += 1
print(f"placed {placed} meshes from engines: {sorted(engines)}")
