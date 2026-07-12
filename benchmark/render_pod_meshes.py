"""render_pod_meshes.py — thumbnail every pod engine's mesh for the list pages.

For each results/listNN/<cat>/<engine>.glb (engine != raw/improved) render
<engine>.png next to it using the SAME renderer/camera as the raw/improved
thumbnails (batch_generate.render_mesh), so the list rows compare like-for-like.

    python render_pod_meshes.py            # renders only missing PNGs
"""
from __future__ import annotations
from pathlib import Path

import trimesh

from batch_generate import render_mesh

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
SKIP = {"raw", "improved"}

done = fail = 0
for glb in sorted(RES.glob("list*/*/*.glb")):
    if glb.stem in SKIP:
        continue
    png = glb.with_suffix(".png")
    if png.exists():
        continue
    try:
        mesh = trimesh.load(glb, force="mesh")
        render_mesh(mesh, png)
        done += 1
        if done % 50 == 0:
            print(f"[render] {done} done", flush=True)
    except Exception as e:
        print(f"[render] FAIL {glb}: {e!r}", flush=True)
        fail += 1
print(f"[render] complete: {done} rendered, {fail} failed", flush=True)
