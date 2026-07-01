"""build_building_ifc.py — turn a building PLACEMENT TABLE into one IFC4 file (+ XKT).

This is the persistence/round-trip backbone for manual editing: after the reviewer drags pieces in
the viewer and we save the new transforms into building_placement.json, this regenerates the BIM file
so the IFC (and the xeokit XKT) reflect the reviewer's decisions.

Reads   deliverable/building/<name>/building_placement.json  (+ asset_library/manifest.json)
Writes  deliverable/building/<name>/<name>.ifc  and (if convertible) <name>.xkt

Coordinates: the placement table is Y-up (x,z on the floor, y = storey elevation), rotation_deg about
the vertical. IFC/BIM is Z-up, so IFC position = [x, z, elevation] and each Z-up asset mesh is rotated
about its Z axis by rotation_deg.

Usage: python build_building_ifc.py <building_name>            # e.g. SCS_Office_Complex
"""
from __future__ import annotations
import sys, os, json, tempfile
from pathlib import Path
import numpy as np
import trimesh
import trimesh.transformations as tf
from math import radians

sys.path.insert(0, str(Path(__file__).parent))
from saveIFC import save_ifc_project

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "deliverable" / "asset_library"


def build(name: str) -> dict:
    bdir = REPO / "deliverable" / "building" / name
    placement = json.load(open(bdir / "building_placement.json", encoding="utf-8"))
    assets = {a["asset_id"]: a for a in json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]}
    tmp = Path(tempfile.mkdtemp(prefix="bldg_ifc_"))

    objects = []
    for inst in placement["instances"]:
        a = assets.get(inst["asset_id"])
        if not a:
            print(f"  [warn] {inst['instance_id']}: asset {inst['asset_id']} not in library; skip"); continue
        m = trimesh.load(str(LIB / a["glb"]), force="mesh")            # Z-up, base at z=0, real-world scale
        rot = float(inst.get("rotation_deg", 0))
        if rot:
            m.apply_transform(tf.rotation_matrix(radians(rot), [0, 0, 1]))  # spin about vertical (Z-up)
        per = tmp / f"{inst['instance_id']}.glb"
        m.export(per)
        objects.append({
            "glbPath": str(per), "name": f"{inst['category']}-{inst['instance_id']}",
            "ifcClass": inst.get("ifc_class", "IfcFurniture"), "category": inst["category"],
            "position": [float(inst["x"]), float(inst["z"]), float(inst["y"])],   # Y-up floor -> Z-up IFC
            "scale": [1, 1, 1],
        })

    out_ifc = str(bdir / f"{name}.ifc")
    res = save_ifc_project(objects, out_ifc)
    ifc_kb = os.path.getsize(out_ifc) // 1024
    print(f"IFC: {len(objects)} instances -> {out_ifc} ({ifc_kb} KB)")

    # XKT for xeokit (optional — needs convert_to_xkt's deps; JSON fallback otherwise)
    xkt_info = None
    try:
        import convert_to_xkt
        xkt_info = convert_to_xkt.convert_ifc_to_xkt(out_ifc, str(bdir / f"{name}.xkt"))
        print(f"XKT: {xkt_info}")
    except SystemExit:
        pass
    except Exception as e:
        print(f"  [warn] XKT conversion skipped: {e}")

    return {"ifc": out_ifc, "instances": len(objects), "ifc_kb": ifc_kb, "xkt": xkt_info}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: build_building_ifc.py <building_name>"); sys.exit(1)
    build(sys.argv[1])
