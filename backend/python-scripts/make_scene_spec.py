"""
make_scene_spec.py — scan office-object photos -> fill the object table (scene_spec.json).

For each image in <photos_dir>, runs the per-object pipeline (run_detect_and_place):
detect the object, estimate real dimensions (Depth Anything Metric), pick/generate
a 3D mesh, and read its IFC class + licence. Each result becomes one ROW in
scene_spec.json — which build_room_scene.py / build_room_ifc.py then turn into a
populated room + IFC.

First run downloads ~300 MB of models (DETR, Depth Anything Small); TripoSR adds
~1.5 GB only if it generates (catalog/primitive rows don't).

Usage:
  python make_scene_spec.py <photos_dir> <out_scene_spec.json> [--room WxDxH] [--meshes <dir>]
Example:
  python make_scene_spec.py data/demo_photos demo/scene_spec.json --room 6x4x3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photos_dir")
    ap.add_argument("out_spec")
    ap.add_argument("--room", default="6x4x3", help="room WxDxH in metres, e.g. 6x4x3")
    ap.add_argument("--meshes", default=None, help="dir for per-object GLBs (default: <out_spec dir>/meshes)")
    args = ap.parse_args()

    import run_detect_and_place

    photos = sorted(p for p in Path(args.photos_dir).iterdir() if p.suffix.lower() in IMAGE_EXT)
    if not photos:
        print(json.dumps({"success": False, "error": f"no images in {args.photos_dir}"}))
        sys.exit(1)

    try:
        w, d, h = (float(x) for x in args.room.lower().split("x"))
    except Exception:
        print(json.dumps({"success": False, "error": f"bad --room '{args.room}', want WxDxH"}))
        sys.exit(1)

    out_spec = Path(args.out_spec)
    out_spec.parent.mkdir(parents=True, exist_ok=True)
    meshes_dir = Path(args.meshes) if args.meshes else out_spec.parent / "meshes"
    meshes_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    objects = []
    for img in photos:
        glb = meshes_dir / (img.stem + ".glb")
        try:
            res = run_detect_and_place.run(str(img), str(glb))
        except Exception as exc:
            print(f"[make_scene_spec] {img.name} failed: {exc}", file=sys.stderr)
            continue
        if not res.get("success"):
            continue
        cat = res.get("category", "furniture")
        counts[cat] = counts.get(cat, 0) + 1
        oid = f"{cat}-{counts[cat]}"
        dims = res["dimensions_m"]
        em = res.get("extra_meta", {})
        objects.append({
            "id": oid,
            "name": cat.replace("_", " ").title(),
            "category": cat,
            "ifc_class": res.get("ifc_class", "IfcFurnishingElement"),
            "dimensions": {"height": dims["height"], "width": dims["width"], "depth": dims["depth"]},
            "glb": str(glb),
            "colour_rgb": res.get("colour_rgb", [0.6, 0.6, 0.62]),
            "source": em.get("source", res.get("mesh_source", "")),
            "license": em.get("license", ""),
        })
        print(f"[make_scene_spec] {img.name} -> {oid} ({res.get('mesh_source')})", file=sys.stderr)

    spec = {"room": {"width": w, "depth": d, "height": h, "name": "Office Room"}, "objects": objects}
    out_spec.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(json.dumps({"success": True, "scene_spec": str(out_spec),
                      "objects": len(objects), "scanned": len(photos)}))


if __name__ == "__main__":
    main()
