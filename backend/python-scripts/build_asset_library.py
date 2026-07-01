"""build_asset_library.py — Phase 1 of building-scale population: the ASSET TABLE.

Consolidates the benchmarked generated meshes into ONE canonical furniture library, each mesh stored
exactly once (decimated + real-world-scaled), described by a manifest row. This is the single source of
truth every room/building placement references by `asset_id` — so a building with 500 chairs stores the
chair mesh once and instances it 500×, instead of duplicating gigabytes of geometry.

Outputs (deliverable/asset_library/):
  <asset_id>.glb        decimated (~10k faces), real-world-scaled, Z-up furniture mesh
  manifest.json         the asset table: [{asset_id, category, source_model, fscore, glb, ifc_class,
                        dimensions_m{width,depth,height}, face_count, license}]

Usage:
  python build_asset_library.py                 # best-of-each cloud model per category
  python build_asset_library.py --all-models    # every model's mesh for every category (more variety)
"""
from __future__ import annotations
import sys, os, csv, json, argparse
from pathlib import Path
import trimesh
import trimesh.transformations as tf
from math import radians
import numpy as np

REPO = Path(__file__).resolve().parents[2]
CLOUD = REPO / "deliverable" / "cloud_results"
ASSETS = REPO / "deliverable" / "cloud_gallery" / "assets"     # front-facing (Y-up) decimated copies
SCORES = REPO / "deliverable" / "cloud_gallery" / "cloud_scores.csv"
LIB = REPO / "deliverable" / "asset_library"

RX_Z_UP = tf.rotation_matrix(radians(90), [1, 0, 0])           # gallery copies are Y-up; library is Z-up
# per-category real-world size in metres (height, width, depth) + IFC class — ergonomic defaults
CATEGORY = {
    "bed":          {"dims": (0.55, 1.5, 2.0), "ifc": "IfcFurniture"},
    "bookshelf":    {"dims": (1.90, 0.9, 0.4), "ifc": "IfcFurniture"},
    "cabinet":      {"dims": (1.20, 1.0, 0.45), "ifc": "IfcFurniture"},
    "chair":        {"dims": (0.90, 0.55, 0.55), "ifc": "IfcChair"},
    "desk":         {"dims": (0.75, 1.4, 0.7), "ifc": "IfcFurniture"},
    "lamp":         {"dims": (1.55, 0.4, 0.4), "ifc": "IfcFurniture"},
    "office_chair": {"dims": (1.10, 0.6, 0.6), "ifc": "IfcChair"},
    "sofa":         {"dims": (0.85, 2.0, 0.9), "ifc": "IfcFurniture"},
    "stool":        {"dims": (0.60, 0.4, 0.4), "ifc": "IfcFurniture"},
    "table":        {"dims": (0.75, 1.2, 0.8), "ifc": "IfcFurniture"},
}
LICENSE = {"triposg": "MIT", "trellis": "MIT", "instantmesh": "Apache-2.0",
           "sam3d": "SAM License (Meta)", "triposr_rembg": "MIT", "triposr_sam2": "MIT"}
TARGET_FACES = 10000


def rows_by_item():
    """(category -> [(model, fscore)]) among models present in cloud_results/."""
    available = {d.name for d in CLOUD.iterdir() if d.is_dir() and d.name != "_bim_catalog"}
    out = {}
    with open(SCORES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["model"] == "abo_gt" or r["model"] not in available:
                continue
            out.setdefault(r["key"], []).append((r["model"], float(r["fscore"])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-models", action="store_true", help="one asset per (category,model) instead of best-of-each")
    ap.add_argument("--faces", type=int, default=TARGET_FACES)
    args = ap.parse_args()
    LIB.mkdir(parents=True, exist_ok=True)

    items = rows_by_item()
    manifest = []
    for cat in sorted(items):
        picks = sorted(items[cat], key=lambda mf: -mf[1])
        picks = picks if args.all_models else picks[:1]
        meta = CATEGORY.get(cat, {"dims": (1.0, 1.0, 1.0), "ifc": "IfcFurniture"})
        H, W, D = meta["dims"]
        for model, fscore in picks:
            src = ASSETS / f"{cat}_{model}.glb"
            if not src.exists():
                src = CLOUD / model / f"{cat}.glb"
            if not src.exists():
                print(f"  skip {cat}/{model}: no mesh"); continue
            asset_id = f"{cat}__{model}"
            m = trimesh.load(str(src), force="mesh")
            m.apply_transform(RX_Z_UP)                                   # -> Z-up (library convention)
            h = float(m.extents[2])
            if h > 1e-6:
                m.apply_scale(H / h)                                     # -> real-world height (m)
            c = m.bounds.mean(axis=0)
            m.apply_translation([-c[0], -c[1], -float(m.bounds[0][2])])  # centre XY, base at z=0
            if len(m.faces) > args.faces:
                m = m.simplify_quadric_decimation(face_count=args.faces)
            glb = LIB / f"{asset_id}.glb"
            m.export(glb)
            dx, dy, dz = (round(float(v), 3) for v in m.extents)
            manifest.append({
                "asset_id": asset_id, "category": cat, "source_model": model,
                "fscore": round(fscore, 3), "glb": glb.name, "ifc_class": meta["ifc"],
                "dimensions_m": {"width": dx, "depth": dy, "height": dz},
                "face_count": int(len(m.faces)), "license": LICENSE.get(model, "unknown"),
            })
            print(f"  {asset_id:24} {dx:.2f}x{dy:.2f}x{dz:.2f} m  {len(m.faces):>5}f  F={fscore:.2f}  {LICENSE.get(model)}")

    (LIB / "manifest.json").write_text(json.dumps({"assets": manifest}, indent=2), encoding="utf-8")
    print(f"\nASSET LIBRARY: {len(manifest)} assets -> {LIB/'manifest.json'}")
    print("categories:", ", ".join(sorted({a['category'] for a in manifest})))


if __name__ == "__main__":
    main()
