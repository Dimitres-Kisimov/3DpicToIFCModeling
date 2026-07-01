"""populate_building.py — populate a REAL architectural building IFC with furniture, ergonomically.

For each IfcSpace (room) it:
  1. reads the room's real footprint + floor level,
  2. extracts the OBSTACLES that intrude into it (internal/party walls, beams, members, columns,
     stairs, railings) as keep-out rectangles, plus door keep-clear zones,
  3. runs the CP-SAT ergonomic solver (spatial_layout + rule_packs: Neufert/Panero/ADA clearances,
     circulation, no-overlap) to place the chosen furniture AROUND the obstacles with no clashes,
  4. merges the placed furniture with the building's empty shell into one populated GLB.

Furniture per room is CHOSEN by the caller (manual), falling back to a per-room-type default only
when no picks are given.  Pure CPU — no GPU.

    python populate_building.py <building.ifc> <out.glb> [--picks picks.json]
    picks.json:  {"Living Room": ["sofa","table","lamp"], "Bedroom 1": ["bed","cabinet"], ...}

Coordinates: IFC is Z-up (floor = XY, Z = vertical); assets are Z-up + real-scaled, so furniture
drops in with a yaw-only rotation. The final scene is rotated to Y-up for the viewer.
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path
import numpy as np
import trimesh
import ifcopenshell, ifcopenshell.geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spatial_layout

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "deliverable" / "asset_library"

# default furniture per room type (used only when the caller gives no explicit picks)
DEFAULT_FURNITURE = {
    "living": ["sofa", "table", "lamp"], "bed": ["bed", "cabinet"],
    "kitchen": ["cabinet", "table"], "dining": ["table", "chair"],
    "office": ["desk", "office_chair"], "study": ["desk", "office_chair"],
    "meeting": ["table", "office_chair"], "lounge": ["sofa", "stool"],
}
SKIP_KEYWORDS = ["bath", "foyer", "hall", "stair", "utility", "roof", "closet", "wc", "corridor"]
# element types that cut up a room and must be avoided
OBSTACLE_TYPES = ["IfcColumn", "IfcWall", "IfcWallStandardCase", "IfcBeam", "IfcMember",
                  "IfcStair", "IfcStairFlight", "IfcRailing"]


def default_picks(name):
    n = (name or "").lower()
    if any(k in n for k in SKIP_KEYWORDS):
        return None
    for kw, items in DEFAULT_FURNITURE.items():
        if kw in n:
            return items
    return None


def load_assets():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], a)
    out = {}
    for cat, a in by_cat.items():
        try:
            out[cat] = {"mesh": trimesh.load(str(LIB / a["glb"]), force="mesh"),
                        "ifc": a["ifc_class"]}
        except Exception:
            pass
    return out


def footprint_rects(f, s, types):
    """World-space footprint rectangles (x0,x1,y0,y1) for every element of the given types."""
    rects = []
    for t in types:
        for e in f.by_type(t):
            if not getattr(e, "Representation", None):
                continue
            try:
                g = ifcopenshell.geom.create_shape(s, e)
                v = np.array(g.geometry.verts).reshape(-1, 3)
                rects.append((v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max(), t))
            except Exception:
                pass
    return rects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc"); ap.add_argument("out")
    ap.add_argument("--picks", default="")
    args = ap.parse_args()

    picks = json.load(open(args.picks, encoding="utf-8")) if args.picks else {}
    f = ifcopenshell.open(args.ifc)
    s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
    assets = load_assets()
    obstacle_rects = footprint_rects(f, s, OBSTACLE_TYPES)     # all structure, once
    door_rects = footprint_rects(f, s, ["IfcDoor"])

    scene = trimesh.Scene()

    # 1) empty shell (everything except furniture + space volumes)
    n_shell = 0
    for prod in f.by_type("IfcProduct"):
        if prod.is_a() in {"IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
                           "IfcSpace", "IfcOpeningElement"} or not getattr(prod, "Representation", None):
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

    placed, rooms_done, skipped_items, clashes = 0, 0, 0, 0
    for sp in f.by_type("IfcSpace"):
        name = sp.LongName or sp.Name or ""
        cats = picks.get(name, picks.get(name.strip()))
        if cats is None:
            cats = default_picks(name)
        if not cats:
            continue
        cats = [c for c in cats if c in assets]
        if not cats:
            continue
        try:
            g = ifcopenshell.geom.create_shape(s, sp)
            v = np.array(g.geometry.verts).reshape(-1, 3)
        except Exception:
            continue
        x0, x1, y0, y1 = v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max()
        fz = v[:, 2].min()
        W, D = x1 - x0, y1 - y0
        if W < 1.2 or D < 1.2:
            continue

        # obstacles intruding into this room's interior (shrink 0.25 m to drop boundary walls)
        keepouts = []
        for (ex0, ex1, ey0, ey1, t) in obstacle_rects:
            ix0, ix1 = max(ex0, x0), min(ex1, x1)
            iy0, iy1 = max(ey0, y0), min(ey1, y1)
            if ix1 - ix0 > 0.05 and iy1 - iy0 > 0.05:                  # overlaps the room
                # keep only genuinely interior intrusions (not the perimeter walls themselves)
                if (ix0 > x0 + 0.25 and ix1 < x1 - 0.25) or (iy0 > y0 + 0.25 and iy1 < y1 - 0.25):
                    keepouts.append({"x": ix0 - x0, "z": iy0 - y0,
                                     "width": ix1 - ix0, "depth": iy1 - iy0})
        # door keep-clear: a 0.9 m buffer in front of any door on this room's edge
        for (dx0, dx1, dy0, dy1, _t) in door_rects:
            if dx1 > x0 and dx0 < x1 and dy1 > y0 and dy0 < y1:
                cx, cy = (dx0 + dx1) / 2 - x0, (dy0 + dy1) / 2 - y0
                keepouts.append({"x": max(0, cx - 0.6), "z": max(0, cy - 0.6),
                                 "width": 1.2, "depth": 1.2})

        # solver objects from the chosen categories (real footprints from the meshes)
        objs, meshmap = [], {}
        for i, cat in enumerate(cats):
            m = assets[cat]["mesh"]; e = m.extents
            if e[0] > W - 0.5 or e[1] > D - 0.5:                       # doesn't fit this room
                skipped_items += 1; continue
            oid = f"{cat}-{i}"
            objs.append({"id": oid, "category": cat,
                         "width": float(e[0]), "depth": float(e[1]), "height": float(e[2])})
            meshmap[oid] = (m, assets[cat]["ifc"])
        if not objs:
            continue

        res = spatial_layout.layout_room({"width": float(W), "depth": float(D), "height": 3.0},
                                         objs, obstacles=keepouts)
        boxes = []   # placed furniture footprints (world) for clash verification
        for p in res["placements"]:
            m, _ifc = meshmap[p["id"]]
            cx, cz = p["position"][0], p["position"][2]
            yaw = float(p["rotation"][1])
            g2 = m.copy()
            if yaw:
                g2.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1]))
            b = g2.bounds
            wx, wy = x0 + cx, y0 + cz
            g2.apply_translation([wx - (b[0][0] + b[1][0]) / 2, wy - (b[0][1] + b[1][1]) / 2, fz - b[0][2]])
            scene.add_geometry(g2, node_name=f"{name}-{p['id']}-{placed}")
            fb = g2.bounds
            boxes.append((fb[0][0], fb[1][0], fb[0][1], fb[1][1]))
            placed += 1
        # verify no furniture-furniture overlap (should be 0 thanks to the solver)
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ax0, ax1, ay0, ay1 = boxes[i]; bx0, bx1, by0, by1 = boxes[j]
                if min(ax1, bx1) - max(ax0, bx0) > 0.02 and min(ay1, by1) - max(ay0, by0) > 0.02:
                    clashes += 1
        rooms_done += 1

    # Z-up (IFC) -> Y-up (viewer)
    scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    scene.export(args.out)
    import os
    print(json.dumps({"ok": True, "out": args.out, "kb": os.path.getsize(args.out) // 1024,
                      "shell_elements": n_shell, "rooms_populated": rooms_done,
                      "furniture_placed": placed, "items_too_big_skipped": skipped_items,
                      "furniture_furniture_clashes": clashes}))


if __name__ == "__main__":
    main()
