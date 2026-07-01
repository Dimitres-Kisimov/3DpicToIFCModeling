"""populate_building.py — populate a REAL architectural building IFC with furniture, ergonomically.

For each IfcSpace (room) it:
  1. reads the room's real footprint + floor level + measures its area,
  2. SMART-SELECTS a sensible, fitting furniture set for that room's TYPE + SIZE (space-aware:
     a small bedroom gets a bed; a big open office gets ~area/6.5 workstations; etc.) — or uses
     the caller's explicit picks,
  3. extracts the OBSTACLES that intrude into the room (internal/party walls, beams, members,
     columns, stairs, railings) as keep-out rectangles, plus door keep-clear zones,
  4. runs the CP-SAT ergonomic solver (spatial_layout + rule_packs: Neufert/Panero/ADA clearances,
     circulation, no-overlap) to place the furniture AROUND the obstacles with no clashes,
  5. merges the placed furniture with the building's empty shell into one populated GLB.

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

SKIP_KEYWORDS = ["bath", "foyer", "hall", "stair", "utility", "roof", "closet", "wc", "corridor"]
# room-name keyword -> canonical room type
TYPE_KEYWORDS = {"living": "living", "lounge": "lounge", "bed": "bed", "kitchen": "kitchen",
                 "dining": "dining", "meeting": "meeting", "conference": "meeting",
                 "office": "office", "study": "office", "work": "office", "room": "living"}
# structural element types that cut up a room and must be avoided
OBSTACLE_TYPES = ["IfcColumn", "IfcWall", "IfcWallStandardCase", "IfcBeam", "IfcMember",
                  "IfcStair", "IfcStairFlight", "IfcRailing"]


def room_type(name):
    """Canonical room type from the IFC room name, or None to skip (bath/hall/stair/…)."""
    n = (name or "").lower()
    if any(k in n for k in SKIP_KEYWORDS):
        return None
    for kw, t in TYPE_KEYWORDS.items():
        if kw in n:
            return t
    return None


def smart_furnish(rt, W, D, assets):
    """Space-aware: a sensible, FITTING furniture set for a room of this type + size (metres).

    Quantities scale with area so a small room isn't overfilled and a large one isn't bare.
    Neufert ~6.5 m²/workstation drives office density; seating/tables scale with area."""
    area = W * D
    items = []
    if rt == "living":
        items += ["sofa"]
        if area > 12: items += ["table"]           # coffee table
        if area > 10: items += ["lamp"]
        if area > 22: items += ["bookshelf"]
    elif rt == "lounge":
        items += ["sofa"] + (["sofa"] if area > 16 else [])
        items += ["stool"] * min(4, max(1, int(area / 8)))
        if area > 12: items += ["lamp"]
    elif rt == "bed":
        items += ["bed"]
        if area > 9:  items += ["cabinet"]         # wardrobe
        if area > 12: items += ["lamp"]
        if area > 17: items += ["desk", "office_chair"]   # study nook in large bedrooms
    elif rt == "kitchen":
        items += ["cabinet"] * min(3, max(1, int(area / 6)))
        if area > 10: items += ["table"]
    elif rt == "office":
        for _ in range(min(8, max(1, int(area / 6.5)))):  # ~6.5 m²/workstation (Neufert)
            items += ["desk", "office_chair"]
        if area > 15: items += ["cabinet"]
        if area > 22: items += ["bookshelf"]
    elif rt == "dining":
        items += ["table"] + ["chair"] * min(8, max(2, int(area / 3)))
    elif rt == "meeting":
        items += ["table"] + ["office_chair"] * min(10, max(2, int(area / 2.5)))
    return [c for c in items if c in assets]


def load_assets():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], a)
    out = {}
    for cat, a in by_cat.items():
        try:
            out[cat] = {"mesh": trimesh.load(str(LIB / a["glb"]), force="mesh"), "ifc": a["ifc_class"]}
        except Exception:
            pass
    return out


def footprint_rects(f, s, types):
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
    ap.add_argument("--movable", default="")   # dir: emit shell.glb + per-piece GLBs + furniture.json
    args = ap.parse_args()

    picks = json.load(open(args.picks, encoding="utf-8")) if args.picks else {}
    f = ifcopenshell.open(args.ifc)
    s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
    assets = load_assets()
    movdir = Path(args.movable) if args.movable else None
    if movdir is not None:
        movdir.mkdir(parents=True, exist_ok=True)
    movable = []
    obstacle_rects = footprint_rects(f, s, OBSTACLE_TYPES)
    door_rects = footprint_rects(f, s, ["IfcDoor"])

    scene = trimesh.Scene()

    # 1) empty shell (everything except furniture + space volumes + openings)
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
    schedule = []
    for sp in f.by_type("IfcSpace"):
        name = sp.LongName or sp.Name or ""
        explicit = picks.get(name, picks.get((name or "").strip()))
        rt = room_type(name)
        if explicit is None and rt is None:                 # not furnishable + not picked
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

        # 2) choose furniture: explicit picks, else space-aware smart set
        if explicit is not None:
            cats = [c for c in explicit if c in assets]
        else:
            cats = smart_furnish(rt, W, D, assets)
        if not cats:
            continue

        # 3) obstacles intruding into this room (shrink 0.25 m to drop the perimeter walls)
        keepouts = []
        for (ex0, ex1, ey0, ey1, t) in obstacle_rects:
            ix0, ix1, iy0, iy1 = max(ex0, x0), min(ex1, x1), max(ey0, y0), min(ey1, y1)
            if ix1 - ix0 > 0.05 and iy1 - iy0 > 0.05:
                if (ix0 > x0 + 0.25 and ix1 < x1 - 0.25) or (iy0 > y0 + 0.25 and iy1 < y1 - 0.25):
                    keepouts.append({"x": ix0 - x0, "z": iy0 - y0, "width": ix1 - ix0, "depth": iy1 - iy0})
        for (dx0, dx1, dy0, dy1, _t) in door_rects:            # door keep-clear
            if dx1 > x0 and dx0 < x1 and dy1 > y0 and dy0 < y1:
                cx, cy = (dx0 + dx1) / 2 - x0, (dy0 + dy1) / 2 - y0
                keepouts.append({"x": max(0, cx - 0.6), "z": max(0, cy - 0.6), "width": 1.2, "depth": 1.2})

        # CP-SAT no-overlap forbids obstacle-obstacle overlap too, so overlapping keep-outs
        # (e.g. a beam sitting inside a wall) would make the room infeasible. Merge them.
        if len(keepouts) > 1:
            from shapely.geometry import box as _box
            from shapely.ops import unary_union
            u = unary_union([_box(k["x"], k["z"], k["x"] + k["width"], k["z"] + k["depth"]) for k in keepouts])
            geoms = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
            keepouts = [{"x": g.bounds[0], "z": g.bounds[1],
                         "width": g.bounds[2] - g.bounds[0], "depth": g.bounds[3] - g.bounds[1]} for g in geoms]

        # 4) solver objects (real footprints); measure out anything too big for the room
        objs, meshmap = [], {}
        for i, cat in enumerate(cats):
            m = assets[cat]["mesh"]; e = m.extents
            if e[0] > W - 0.5 or e[1] > D - 0.5:
                skipped_items += 1; continue
            oid = f"{cat}-{i}"
            objs.append({"id": oid, "category": cat,
                         "width": float(e[0]), "depth": float(e[1]), "height": float(e[2])})
            meshmap[oid] = assets[cat]["mesh"]
        if not objs:
            continue

        # fit-as-many-as-possible: shrink the priority-ordered set until the solver places them
        # ALL cleanly (placed=True) — guarantees no clashes while keeping the most important pieces
        room_objs, res = list(objs), None
        while room_objs:
            res = spatial_layout.layout_room({"width": float(W), "depth": float(D), "height": 3.0},
                                             room_objs, obstacles=keepouts)
            if all(p.get("placed", True) for p in res["placements"]):
                break
            room_objs.pop(); skipped_items += 1          # drop lowest-priority item, retry
        if not room_objs or res is None:
            continue
        boxes, room_cats = [], []
        for p in res["placements"]:
            m = meshmap[p["id"]]
            cx, cz, yaw = p["position"][0], p["position"][2], float(p["rotation"][1])
            if yaw:   # solver reports the centre from the UN-rotated footprint — correct the 90° swap
                ex_, ey_ = float(m.extents[0]), float(m.extents[1])
                cx += (ey_ - ex_) / 2
                cz += (ex_ - ey_) / 2
            wx, wy, cat = x0 + cx, y0 + cz, p["id"].rsplit("-", 1)[0]
            if movdir is not None:
                # export the piece centred at footprint origin (base at 0), Y-up; the viewer positions
                # it — so each piece is a separate, movable object (drag-to-reposition).
                piece = m.copy()
                if yaw:
                    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1]))
                pb = piece.bounds
                piece.apply_translation([-(pb[0][0] + pb[1][0]) / 2, -(pb[0][1] + pb[1][1]) / 2, -pb[0][2]])
                piece.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # Z-up->Y-up
                gname = f"piece_{placed}.glb"
                piece.export(str(movdir / gname))
                movable.append({"id": f"{cat}-{placed}", "room": name, "category": cat, "glb": gname,
                                "pos": [round(wx, 3), round(fz, 3), round(-wy, 3)]})   # Y-up world
                boxes.append((wx - m.extents[0] / 2, wx + m.extents[0] / 2, wy - m.extents[1] / 2, wy + m.extents[1] / 2))
            else:
                g2 = m.copy()
                if yaw:
                    g2.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1]))
                b = g2.bounds
                g2.apply_translation([wx - (b[0][0] + b[1][0]) / 2, wy - (b[0][1] + b[1][1]) / 2, fz - b[0][2]])
                scene.add_geometry(g2, node_name=f"{name}-{cat}-{placed}")
                fb = g2.bounds
                boxes.append((fb[0][0], fb[1][0], fb[0][1], fb[1][1]))
            room_cats.append(cat)
            placed += 1
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ax0, ax1, ay0, ay1 = boxes[i]; bx0, bx1, by0, by1 = boxes[j]
                if min(ax1, bx1) - max(ax0, bx0) > 0.02 and min(ay1, by1) - max(ay0, by0) > 0.02:
                    clashes += 1
        schedule.append({"room": name, "type": rt or "picked", "area_m2": round(W * D, 1),
                         "placed": len(boxes), "items": room_cats})
        rooms_done += 1

    scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))   # -> Y-up
    import os
    if movdir is not None:
        scene.export(str(movdir / "shell.glb"))            # scene holds only the shell in movable mode
        (movdir / "furniture.json").write_text(json.dumps({"pieces": movable}), encoding="utf-8")
        out_info = {"shell": "shell.glb", "movable_pieces": len(movable)}
    else:
        scene.export(args.out)
        out_info = {"out": args.out, "kb": os.path.getsize(args.out) // 1024}
    print(json.dumps({"ok": True, **out_info, "shell_elements": n_shell, "rooms_populated": rooms_done,
                      "furniture_placed": placed, "items_too_big_skipped": skipped_items,
                      "furniture_furniture_clashes": clashes, "schedule": schedule}))


if __name__ == "__main__":
    main()
