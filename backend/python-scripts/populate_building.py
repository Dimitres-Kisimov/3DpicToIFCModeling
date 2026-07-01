"""populate_building.py — auto-populate a REAL architectural building IFC with furniture.

Reads every IfcSpace (room) from a building IFC, assigns furniture by room name/type from the
asset library, places it inside each room's real footprint (seated on the floor), and merges the
result with the building's empty shell into ONE populated GLB. Pure CPU — no GPU.

    python populate_building.py <building.ifc> <out.glb> [--rooms Living,Bedroom,...]

Coordinates: IFC is Z-up (floor = XY plane, Z = vertical). Our asset meshes are also Z-up and
real-world scaled, so furniture drops straight in. The whole scene is rotated to Y-up at the end
so it displays upright in a standard glTF/xeokit viewer.
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path
import numpy as np
import trimesh
import ifcopenshell, ifcopenshell.geom

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "deliverable" / "asset_library"

# room-name keyword -> furniture categories (from the asset library) to place in that room
ROOM_FURNITURE = {
    "living":  ["sofa", "table", "lamp", "bookshelf"],
    "bed":     ["bed", "cabinet", "lamp"],
    "kitchen": ["cabinet", "cabinet", "table"],
    "dining":  ["table", "chair", "chair"],
    "office":  ["desk", "office_chair", "bookshelf"],
    "study":   ["desk", "office_chair"],
    "meeting": ["table", "office_chair", "office_chair"],
    "lounge":  ["sofa", "stool", "lamp"],
}
SKIP_KEYWORDS = ["bath", "foyer", "hall", "stair", "utility", "roof", "closet", "wc", "corridor"]


def room_furniture(name: str):
    n = (name or "").lower()
    if any(k in n for k in SKIP_KEYWORDS):
        return None
    for kw, items in ROOM_FURNITURE.items():
        if kw in n:
            return items
    return None   # unknown room -> leave empty (safe default)


def load_asset_meshes():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], a)   # first asset per category
    meshes = {}
    for cat, a in by_cat.items():
        try:
            meshes[cat] = trimesh.load(str(LIB / a["glb"]), force="mesh")
        except Exception:
            pass
    return meshes


def place_asset(mesh: trimesh.Trimesh, cx, cy, floor_z):
    """Copy the asset, seat its base on floor_z and centre its footprint at (cx, cy). Z-up."""
    g = mesh.copy()
    b = g.bounds  # [[minx,miny,minz],[maxx,maxy,maxz]]
    fx = (b[0][0] + b[1][0]) / 2
    fy = (b[0][1] + b[1][1]) / 2
    g.apply_translation([cx - fx, cy - fy, floor_z - b[0][2]])
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("out")
    args = ap.parse_args()

    f = ifcopenshell.open(args.ifc)
    s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
    assets = load_asset_meshes()
    scene = trimesh.Scene()

    # 1) the empty shell: everything except furniture and space volumes
    SKIP_TYPES = {"IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement", "IfcSpace"}
    n_shell = 0
    for prod in f.by_type("IfcProduct"):
        if prod.is_a() in SKIP_TYPES or not getattr(prod, "Representation", None):
            continue
        try:
            sh = ifcopenshell.geom.create_shape(s, prod)
            v = np.array(sh.geometry.verts).reshape(-1, 3)
            fc = np.array(sh.geometry.faces).reshape(-1, 3)
            if len(v) and len(fc):
                scene.add_geometry(trimesh.Trimesh(vertices=v, faces=fc), node_name=f"shell-{n_shell}")
                n_shell += 1
        except Exception:
            pass

    # 2) per room: read footprint, assign furniture, place it inside
    placed, rooms_done, schedule = 0, 0, []
    for sp in f.by_type("IfcSpace"):
        name = sp.LongName or sp.Name or ""
        cats = room_furniture(name)
        if not cats:
            continue
        try:
            g = ifcopenshell.geom.create_shape(s, sp)
            v = np.array(g.geometry.verts).reshape(-1, 3)
        except Exception:
            continue
        x0, x1 = v[:, 0].min(), v[:, 0].max()
        y0, y1 = v[:, 1].min(), v[:, 1].max()
        floor_z = v[:, 2].min()
        M = 0.4  # wall margin
        ux0, ux1, uy0, uy1 = x0 + M, x1 - M, y0 + M, y1 - M
        if ux1 <= ux0 or uy1 <= uy0:
            continue
        # lay the room's furniture along its longer axis, centred on the shorter
        cats = [c for c in cats if c in assets]
        if not cats:
            continue
        along_x = (ux1 - ux0) >= (uy1 - uy0)
        span = (ux1 - ux0) if along_x else (uy1 - uy0)
        step = span / (len(cats) + 1)
        cross = (uy0 + uy1) / 2 if along_x else (ux0 + ux1) / 2
        for i, cat in enumerate(cats):
            t = (i + 1) * step
            cx, cy = (ux0 + t, cross) if along_x else (cross, uy0 + t)
            m = assets[cat]
            # skip if the item is bigger than the room footprint
            e = m.extents
            if e[0] > (x1 - x0) or e[1] > (y1 - y0):
                continue
            scene.add_geometry(place_asset(m, cx, cy, floor_z), node_name=f"{name}-{cat}-{placed}")
            schedule.append({"room": name, "category": cat, "x": round(float(cx), 2),
                             "y": round(float(cy), 2), "z": round(float(floor_z), 2)})
            placed += 1
        rooms_done += 1

    # 3) Z-up (IFC) -> Y-up (glTF standard) so it stands upright in the viewer
    R = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    scene.apply_transform(R)

    scene.export(args.out)
    import os
    b = scene.bounds
    print(json.dumps({
        "ok": True, "out": args.out, "kb": os.path.getsize(args.out) // 1024,
        "shell_elements": n_shell, "rooms_populated": rooms_done, "furniture_placed": placed,
        "bbox_m": [round(float(b[1][i] - b[0][i]), 1) for i in range(3)],
        "schedule": schedule,
    }))


if __name__ == "__main__":
    main()
