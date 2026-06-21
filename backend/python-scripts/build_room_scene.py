"""
build_room_scene.py — Populate-layer for the room demo (Sim B).

Takes a *scene spec* (room dimensions + a list of furniture objects, each with
real-world dimensions and an optional GLB mesh) and produces, in <out_dir>:

  scene.glb       combined geometry: room shell + furniture placed by the solver
  metamodel.json  xeokit MetaModel — named/typed/pickable objects for the viewer
  schedule.json   the object table (id, name, ifc_class, W/D/H, qty, material,
                  source, license) — drives the export table
  schedule.csv    same, spreadsheet-friendly

Placement uses the CP-SAT solver (spatial_layout.py) when OR-Tools is installed,
otherwise a deterministic grid fallback — so the demo runs even without OR-Tools
(important on bleeding-edge Python where the ortools wheel may be missing).

Coordinate conventions:
  * Per-object GLBs from run_detect_and_place are Z-up (trimesh default).
  * The solver and xeokit use Y-up, floor on the XZ plane.
  This script converts each object Z-up -> Y-up, applies the solver's Y-rotation,
  and seats it on the floor.

Usage:
  python build_room_scene.py <scene_spec.json> <out_dir>

scene_spec.json:
{
  "room": {"width": 6.0, "depth": 4.0, "height": 3.0, "name": "Office Room"},
  "objects": [
    {"id": "chair-1", "name": "Office Chair", "category": "office_chair",
     "ifc_class": "IfcChair",
     "dimensions": {"height": 0.95, "width": 0.55, "depth": 0.55},
     "glb": "outputs/chair-1.glb", "colour_rgb": [0.2, 0.2, 0.22],
     "source": "TripoSR (Stability AI)", "license": "MIT"}
  ]
}
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))


# ---------------------------------------------------------------------------
# Placement: CP-SAT solver if available, else deterministic grid
# ---------------------------------------------------------------------------
def _placements(room: dict, objects: list) -> list:
    solver_objs = [
        {
            "id": o["id"],
            "width": float(o["dimensions"]["width"]),
            "depth": float(o["dimensions"]["depth"]),
            "category": o.get("category", "default"),
        }
        for o in objects
    ]
    try:
        import spatial_layout  # noqa: WPS433 (local import — optional dep)

        result = spatial_layout.layout_room(room, solver_objs)
        return result["placements"], "ortools-cpsat"
    except Exception as exc:  # OR-Tools missing or solve failed -> grid fallback
        print(f"[build_room_scene] solver unavailable ({exc}); grid fallback", file=sys.stderr)
        return _grid_fallback(room, solver_objs), "grid-fallback"


def _grid_fallback(room: dict, objs: list) -> list:
    """Lay objects out on a margin-respecting grid, no overlap, deterministic."""
    margin = 0.4
    x = margin
    z = margin
    row_depth = 0.0
    out = []
    for o in objs:
        w, d = o["width"], o["depth"]
        if x + w + margin > room["width"]:
            x = margin
            z += row_depth + margin
            row_depth = 0.0
        cx = x + w / 2
        cz = z + d / 2
        out.append({"id": o["id"], "position": [round(cx, 3), 0.0, round(cz, 3)],
                    "rotation": [0, 0, 0], "placed": True})
        x += w + margin
        row_depth = max(row_depth, d)
    return out


# ---------------------------------------------------------------------------
# Geometry assembly (Y-up combined GLB)
# ---------------------------------------------------------------------------
_ROTX_NEG90 = trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])


def _coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    try:
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=np.array([rgb[0], rgb[1], rgb[2], 1.0]),
                roughnessFactor=0.7, metallicFactor=0.0,
            )
        )
    except Exception:
        pass
    return mesh


def _category_primitive(category: str, h: float, w: float, d: float) -> trimesh.Trimesh:
    """Recognisable primitive (chair = seat+back+legs, desk = top+legs, shelf = shelves)
    instead of a plain box — reuses the builders from run_detect_and_place."""
    try:
        import run_detect_and_place as rdp
        builder = rdp.CATEGORY_MESH_BUILDERS.get(category, rdp._box_mesh)
        return builder(h, w, d)
    except Exception:
        return trimesh.creation.box(extents=[w, d, h])


def _object_mesh(obj: dict) -> trimesh.Trimesh:
    """Return a Y-up, origin-centred mesh sized to the object's real dimensions."""
    dims = obj["dimensions"]
    h, w, d = float(dims["height"]), float(dims["width"]), float(dims["depth"])
    glb = obj.get("glb")
    mesh = None
    is_glb = False
    if glb and Path(glb).exists():
        try:
            loaded = trimesh.load(glb, force="mesh")
            if isinstance(loaded, trimesh.Scene):
                loaded = trimesh.util.concatenate(
                    [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
                )
            if loaded.vertices.shape[0] > 0:
                mesh = loaded
                is_glb = True
        except Exception:
            mesh = None
    if mesh is None:
        # Recognisable primitive (chair/desk/shelf/...) — built Z-up
        mesh = _category_primitive(obj.get("category", ""), h, w, d)

    mesh.apply_translation(-mesh.bounding_box.centroid)
    if not is_glb:
        # procedural primitives are Z-up; glTF/GLB meshes are already Y-up
        mesh.apply_transform(_ROTX_NEG90)
    # scale to the object's real (ergonomic) dimensions: X=width, Y=height, Z=depth
    ext = mesh.extents
    if all(e > 1e-6 for e in ext):
        mesh.apply_scale([w / ext[0], h / ext[1], d / ext[2]])
    return _coloured(mesh, obj.get("colour_rgb", [0.6, 0.6, 0.62]))


def _place(mesh: trimesh.Trimesh, position, rotation_deg_y: float,
           elevation: float = 0.0) -> trimesh.Trimesh:
    m = mesh.copy()
    if rotation_deg_y:
        m.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(rotation_deg_y), [0, 1, 0]))
    cx, _, cz = position
    bb_min, bb_max = m.bounds
    centroid = (bb_min + bb_max) / 2.0
    tx = cx - centroid[0]
    tz = cz - centroid[2]
    ty = elevation - bb_min[1]  # seat base on the floor, or on top of an anchor
    m.apply_translation([tx, ty, tz])
    return m


def _chair_forward_xz(obj):
    """Native forward (backrest -> seat-front) of a seat mesh in its Y-up XZ plane,
    so we can turn the chair to face the desk regardless of the source mesh's
    orientation. Backrest = upper mass at the rear; seat-front is the opposite way."""
    try:
        m = _object_mesh(obj)
        v = m.vertices
        y = v[:, 1]
        y0, y1 = float(y.min()), float(y.max())
        h = y1 - y0
        if h < 1e-6:
            return (0.0, 1.0)
        back = v[y > y0 + 0.6 * h][:, [0, 2]]   # backrest (upper band)
        seat = v[y < y0 + 0.5 * h][:, [0, 2]]   # seat (lower band)
        if len(back) < 10 or len(seat) < 10:
            return (0.0, 1.0)
        fwd = seat.mean(axis=0) - back.mean(axis=0)   # back -> front
        n = float((fwd[0] ** 2 + fwd[1] ** 2) ** 0.5)
        return (float(fwd[0] / n), float(fwd[1] / n)) if n > 1e-6 else (0.0, 1.0)
    except Exception:
        return (0.0, 1.0)


def _resolve_layout(room: dict, objects: list):
    """Solve free-standing objects with CP-SAT, then place 'anchored' objects
    functionally relative to their anchor — chair in front of desk (facing it),
    monitor on top of desk. This is the human/functional layer pure packing lacks.

    Anchor spec on an object: {"anchor": {"to": "<id>", "relation": "in_front"|"on_top"|"beside"}}
    """
    by_id = {o["id"]: o for o in objects}
    cw, ch = float(room["width"]), float(room["depth"])
    cx, cz = cw / 2.0, ch / 2.0
    GAP = 0.12

    direct = {}
    for o in objects:
        a = o.get("anchor")
        if a:
            direct.setdefault(a["to"], []).append(o)
    free = [o for o in objects if not o.get("anchor")]

    # Reserve each group's full footprint in the solve: a desk's in-front chair and
    # a parent's beside-child expand its solver box, so groups can't collide.
    solver_objs, meta = [], {}
    for o in free:
        w = float(o["dimensions"]["width"]); d = float(o["dimensions"]["depth"])
        extra_d = 0.0; extra_w = 0.0; front_w = w
        for c in direct.get(o["id"], []):
            rel = c["anchor"].get("relation", "in_front")
            cwd = float(c["dimensions"]["width"]); cdd = float(c["dimensions"]["depth"])
            if rel == "in_front":
                extra_d = max(extra_d, GAP + cdd); front_w = max(front_w, cwd)
            elif rel == "beside":
                extra_w += GAP + cwd
        solver_objs.append({"id": o["id"], "width": max(w, front_w) + extra_w,
                            "depth": d + extra_d, "category": o.get("category", "")})
        meta[o["id"]] = {"w": w, "d": d, "extra_d": extra_d}

    try:
        import spatial_layout
        placements = spatial_layout.layout_room(room, solver_objs)["placements"]
        solver = "ortools-cpsat"
    except Exception as exc:
        print(f"[build_room_scene] solver unavailable ({exc}); grid fallback", file=sys.stderr)
        placements = _grid_fallback(room, solver_objs)
        solver = "grid-fallback"
    box = {p["id"]: p for p in placements}
    pos = {}

    def _face(child, px, pz, ax, az):
        target = math.degrees(math.atan2(ax - px, az - pz))   # child -> anchor
        if "chair" in child.get("category", ""):
            fx, fz = _chair_forward_xz(child)
            return target - math.degrees(math.atan2(fx, fz))  # seat-front -> anchor
        return target

    for o in free:
        b = box.get(o["id"])
        if b is None:
            continue
        m = meta[o["id"]]
        bx, _, bz = b["position"]
        rot = (b.get("rotation") or [0, 0, 0])[1]
        along_z = (round(rot / 90) % 2 == 0)
        # anchor at the wall end of the reserved box; "front" points to the room
        if along_z:
            front = 1.0 if cz > bz else -1.0
            ax, az = bx, bz - front * m["extra_d"] / 2.0
        else:
            front = 1.0 if cx > bx else -1.0
            ax, az = bx - front * m["extra_d"] / 2.0, bz
        pos[o["id"]] = {"id": o["id"], "position": [ax, 0.0, az],
                        "rotation": [0, rot, 0], "placed": True}
        for c in direct.get(o["id"], []):
            rel = c["anchor"].get("relation", "in_front")
            cdd = float(c["dimensions"]["depth"]); cwd = float(c["dimensions"]["width"])
            if rel == "on_top":
                ox, oz = (c["anchor"].get("offset", [0.0, 0.0]) + [0.0, 0.0])[:2]
                pos[c["id"]] = {"id": c["id"], "position": [ax + float(ox), 0.0, az + float(oz)],
                                "rotation": [0, rot, 0],
                                "elevation": float(o["dimensions"]["height"]), "placed": True}
            elif rel == "beside":
                off = m["w"] / 2 + cwd / 2 + 0.1
                px, pz = (ax + off, az) if along_z else (ax, az + off)
                pos[c["id"]] = {"id": c["id"], "position": [px, 0.0, pz],
                                "rotation": [0, rot, 0], "placed": True}
            else:  # in_front — toward the room, seat facing the anchor
                off = m["d"] / 2 + GAP + cdd / 2
                px, pz = (ax, az + front * off) if along_z else (ax + front * off, az)
                pos[c["id"]] = {"id": c["id"], "position": [px, 0.0, pz],
                                "rotation": [0, _face(c, px, pz, ax, az), 0], "placed": True}

    # nested children (e.g. stool beside coffee-table) — place after their parent
    for o in [x for x in objects if x.get("anchor") and x["id"] not in pos]:
        a = o["anchor"]; ref = pos.get(a["to"])
        if ref is None:
            continue
        rx, _, rz = ref["position"]; rrot = (ref.get("rotation") or [0, 0, 0])[1]
        ad = by_id[a["to"]]["dimensions"]; od = o["dimensions"]
        rel = a.get("relation", "in_front")
        if rel == "on_top":
            ox, oz = (a.get("offset", [0.0, 0.0]) + [0.0, 0.0])[:2]
            pos[o["id"]] = {"id": o["id"], "position": [rx + float(ox), 0.0, rz + float(oz)],
                            "rotation": [0, rrot, 0], "elevation": float(ad["height"]), "placed": True}
        elif rel == "beside":
            off = float(ad["width"]) / 2 + float(od["width"]) / 2 + 0.1
            pos[o["id"]] = {"id": o["id"], "position": [rx + off, 0.0, rz],
                            "rotation": [0, rrot, 0], "placed": True}
        else:
            off = float(ad["depth"]) / 2 + float(od["depth"]) / 2 + GAP
            pos[o["id"]] = {"id": o["id"], "position": [rx, 0.0, rz + off],
                            "rotation": [0, _face(o, rx, rz + off, rx, rz), 0], "placed": True}
    return pos, solver


def _room_shell(room: dict):
    """Floor + back wall + left wall (dollhouse view), as named Y-up meshes."""
    w, d, h = float(room["width"]), float(room["depth"]), float(room["height"])
    t = 0.08
    floor = trimesh.creation.box(extents=[w, 0.05, d])
    floor.apply_translation([w / 2, -0.025, d / 2])
    wall_back = trimesh.creation.box(extents=[w, h, t])
    wall_back.apply_translation([w / 2, h / 2, t / 2])
    wall_left = trimesh.creation.box(extents=[t, h, d])
    wall_left.apply_translation([t / 2, h / 2, d / 2])
    return {
        "room-floor": (_coloured(floor, [0.82, 0.80, 0.76]), "Floor", "IfcSlab"),
        "room-wall-back": (_coloured(wall_back, [0.90, 0.90, 0.88]), "Wall (back)", "IfcWall"),
        "room-wall-left": (_coloured(wall_left, [0.90, 0.90, 0.88]), "Wall (left)", "IfcWall"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build(spec: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    room = spec["room"]
    objects = spec["objects"]

    pos_by_id, solver = _resolve_layout(room, objects)

    geometry = {}
    meta_objects = [{"id": "room", "name": room.get("name", "Room"),
                     "type": "IfcSpace", "parent": None}]

    # Room shell
    for node_id, (mesh, name, ifc) in _room_shell(room).items():
        geometry[node_id] = mesh
        meta_objects.append({"id": node_id, "name": name, "type": ifc, "parent": "room"})

    # Furniture
    schedule = []
    for obj in objects:
        p = pos_by_id.get(obj["id"])
        if p is None:
            continue
        rot_y = p["rotation"][1] if isinstance(p.get("rotation"), list) else 0
        placed = _place(_object_mesh(obj), p["position"], rot_y, p.get("elevation", 0.0))
        geometry[obj["id"]] = placed
        meta_objects.append({"id": obj["id"], "name": obj.get("name", obj["id"]),
                             "type": obj.get("ifc_class", "IfcFurnishingElement"), "parent": "room"})
        dims = obj["dimensions"]
        rgb = obj.get("colour_rgb", [0.6, 0.6, 0.62])
        schedule.append({
            "id": obj["id"],
            "name": obj.get("name", obj["id"]),
            "ifc_class": obj.get("ifc_class", "IfcFurnishingElement"),
            "category": obj.get("category", ""),
            "width_m": round(float(dims["width"]), 3),
            "depth_m": round(float(dims["depth"]), 3),
            "height_m": round(float(dims["height"]), 3),
            "qty": 1,
            "material_hex": "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in rgb),
            "x": p["position"][0], "z": p["position"][2], "rotation_deg": rot_y,
            "source": obj.get("source", ""),
            "license": obj.get("license", ""),
        })

    # Export combined GLB
    scene = trimesh.Scene(geometry=geometry)
    glb_path = out_dir / "scene.glb"
    scene.export(str(glb_path))

    # MetaModel (xeokit)
    (out_dir / "metamodel.json").write_text(
        json.dumps({"metaObjects": meta_objects}, indent=2), encoding="utf-8")

    # Schedule JSON + CSV
    (out_dir / "schedule.json").write_text(
        json.dumps({"room": room, "solver": solver, "items": schedule}, indent=2),
        encoding="utf-8")
    if schedule:
        with open(out_dir / "schedule.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(schedule[0].keys()))
            writer.writeheader()
            writer.writerows(schedule)

    return {
        "success": True,
        "out_dir": str(out_dir),
        "solver": solver,
        "object_count": len(schedule),
        "glb_bytes": glb_path.stat().st_size,
        "outputs": ["scene.glb", "metamodel.json", "schedule.json", "schedule.csv"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"success": False,
                          "error": "Usage: build_room_scene.py <scene_spec.json> <out_dir>"}))
        sys.exit(1)
    try:
        spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        print(json.dumps(build(spec, Path(sys.argv[2]))))
    except Exception as exc:
        import traceback
        print(json.dumps({"success": False, "error": str(exc),
                          "traceback": traceback.format_exc()}))
        sys.exit(1)
