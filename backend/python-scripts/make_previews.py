"""
make_previews.py — render clean colored thumbnails for all 400 ABO meshes.

The dataset ships dark silhouette thumbnails that are hard to tell apart in the picker.
This renders a proper 3/4 view on white (trimesh, headless) into the catalogue folder as
<glb_stem>.preview.png, which the per-item picker prefers over the silhouette.

Run: python backend/python-scripts/make_previews.py [--res 256] [--force]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import trimesh

REPO = Path(__file__).resolve().parents[2]
ABO = REPO / "data" / "mesh_library_abo"


def render_one(glb: Path, out_png: Path, res: int):
    s = trimesh.load(str(glb))
    scene = s if isinstance(s, trimesh.Scene) else s.scene()
    scene.set_camera(angles=(math.radians(-25), math.radians(-35), 0))
    out_png.write_bytes(scene.save_image(resolution=(res, res), visible=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=256)
    ap.add_argument("--force", action="store_true", help="re-render even if a preview exists")
    args = ap.parse_args()

    man = json.loads((ABO / "manifest.json").read_text(encoding="utf-8"))
    ok = skip = fail = 0
    for i, e in enumerate(man, 1):
        glb = ABO / e["glb"]
        out = ABO / (Path(e["glb"]).stem + ".preview.png")
        if out.exists() and not args.force:
            skip += 1; continue
        try:
            render_one(glb, out, args.res)
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"  [{i}/{len(man)}] FAIL {e['id']}: {str(exc)[:70]}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  {i}/{len(man)}  (rendered={ok} skipped={skip} failed={fail})", flush=True)
    print(f"DONE: rendered={ok} skipped={skip} failed={fail} -> {ABO}/*.preview.png")


if __name__ == "__main__":
    main()
