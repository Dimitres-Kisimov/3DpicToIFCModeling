"""make_studyE_views.py — build Study E's multi-view test set from ground truth.

For each deliverable/cloud_bundle/gt/<key>.glb, render 4 views (az 0/90/180/270,
el 15) with the same renderer as the benchmark thumbnails. Writes
deliverable/cloud_bundle/studyE_views/<key>_az{NNN}.png and studyE_manifest.json
(one item per OBJECT, listing its 4 views + the gt path — the multi-image
counterpart of manifest.json, scoreable by the same eval).

    python make_studyE_views.py
"""
from __future__ import annotations
import json
from pathlib import Path

import trimesh

from batch_generate import render_mesh

HERE = Path(__file__).resolve().parent
CB = HERE.parent / "deliverable" / "cloud_bundle"
GT = CB / "gt"
OUT = CB / "studyE_views"
OUT.mkdir(exist_ok=True)

AZIMUTHS = [0, 90, 180, 270]
items = []
for glb in sorted(GT.glob("*.glb")):
    key = glb.stem
    mesh = trimesh.load(glb, force="mesh")
    views = []
    for az in AZIMUTHS:
        png = OUT / f"{key}_az{az:03d}.png"
        if not png.exists():
            render_mesh(mesh, png, az=az, el=15)
        views.append(f"studyE_views/{png.name}")
    items.append({"key": key, "type": key, "views": views, "gt": f"gt/{glb.name}",
                  "source_id": f"studyE:{key}"})
    print(f"[studyE] {key}: 4 views")

json.dump(items, open(CB / "studyE_manifest.json", "w", encoding="utf-8"), indent=1)
print(f"[studyE] manifest: {len(items)} objects x 4 views")
