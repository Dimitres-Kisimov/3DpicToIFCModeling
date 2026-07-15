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

import rule_packs  # noqa: E402  (archetypes drive wall mounting + centring)


# ---------------------------------------------------------------------------
# Placement: CP-SAT solver if available, else deterministic grid
# ---------------------------------------------------------------------------
def _placements(room: dict, objects: list) -> list:
    solver_objs = [
        {
            "id": o["id"],
            "width": float(o["dimensions"]["width"]),
            "depth": float(o["dimensions"]["depth"]),
            "height": float(o["dimensions"].get("height", 0.0)),  # lets the solver's tall-item wall rule fire
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


# On-desk electronics must FACE the person at the desk. The procedural monitor/
# laptop meshes carry their screen on the local -Z side after Z-up -> Y-up
# conversion (the laptop hinges at the rear edge), so a half-turn relative to
# the desk points the screen at the chair.
_SCREEN_FLIP = {"monitor": 180.0, "laptop": 180.0}


def _presentation_prepass(room, objects):
    """Presentation halls — the user's standing rules ('never forget this'):
    the display (screen, else whiteboard) owns the front wall; chair rows FACE
    it, are CENTERED on its axis, and start at the required viewing distance
    (~1.5x image width, min 2.3 m); the projector hangs from the CEILING at
    2.20 m (ASR A1.8 headroom kept underneath), aimed at the display at throw
    distance. Mirrors the building-path row engine. Consumed objects skip the
    CP-SAT solve; floor items become keep-outs for it."""
    W, D = float(room["width"]), float(room["depth"])
    pos, keep, consumed = {}, [], set()

    def _dims(o):
        return float(o["dimensions"]["width"]), float(o["dimensions"]["depth"])

    def _take(cat):
        for o in objects:
            if o.get("category") == cat and o["id"] not in consumed and not o.get("anchor"):
                consumed.add(o["id"])
                return o
        return None

    def _rect_free(x, z, w, d):
        for k in list(room.get("obstacles", [])) + list(room.get("doors", [])) + keep:
            if (min(x + w / 2, k["x"] + k["width"]) - max(x - w / 2, k["x"]) > 0.02
                    and min(z + d / 2, k["z"] + k["depth"]) - max(z - d / 2, k["z"]) > 0.02):
                return False
        return True

    def _put(o, x, z, yaw, elev=None, block=True):
        p = {"id": o["id"], "position": [x, 0.0, z], "rotation": [0, yaw, 0], "placed": True}
        if elev is not None:
            p["elevation"] = elev
        pos[o["id"]] = p
        if block:
            w, d = _dims(o)
            keep.append({"x": x - w / 2 - 0.05, "z": z - d / 2 - 0.05,
                         "width": w + 0.10, "depth": d + 0.10})

    disp, disp_cx, img_w = None, W / 2, 2.0
    scr = _take("presentation_screen")
    if scr is not None:
        w, d = _dims(scr)
        _put(scr, W / 2, d / 2 + 0.03, 0, elev=0.8, block=False)     # front wall, eye height
        scr["anchor"] = {"to": "front_wall", "relation": "mounted_on"}
        disp, disp_cx, img_w = scr, W / 2, w
    wb = _take("whiteboard")
    if wb is not None:
        w, d = _dims(wb)
        cx = W * 0.15 + w / 2
        if scr is not None:                       # keep clear of the screen
            cx = min(cx, W / 2 - _dims(scr)[0] / 2 - w / 2 - 0.10)
        if cx - w / 2 >= 0.05:
            _put(wb, cx, d / 2 + 0.03, 0, elev=0.9, block=False)
            wb["anchor"] = {"to": "front_wall", "relation": "mounted_on"}
            if disp is None:                      # no screen: whiteboard IS the display
                disp, disp_cx, img_w = wb, cx, w
        else:
            consumed.discard(wb["id"])            # no wall room left: back to the solver
    lec = _take("lectern")
    if lec is not None:
        w, d = _dims(lec)
        if _rect_free(W * 0.22, 1.0, w, d):
            _put(lec, W * 0.22, 1.0, 180)                            # faces the audience
            lec["anchor"] = {"to": "audience", "relation": "faces"}
        else:
            consumed.discard(lec["id"])
    proj = _take("projector")
    if proj is not None:
        throw = min(3.5, max(1.5, 1.2 * img_w))
        pz = min(max(throw, 1.2), D - 0.8)
        px = min(max(disp_cx, 0.5), W - 0.5)
        pyaw = math.degrees(math.atan2(disp_cx - px, 0.06 - pz))     # lens -> display
        _put(proj, px, pz, pyaw, elev=2.2, block=False)              # >=2.10 m headroom
        proj["anchor"] = {"to": disp["id"] if disp else "front_wall",
                          "relation": "throws_onto"}

    chairs = [o for o in objects
              if o.get("category") in ("chair", "office_chair", "armchair", "stool")
              and o["id"] not in consumed and not o.get("anchor")]
    if chairs:
        sw, sd = _dims(chairs[0])
        pitch_x = sw + 0.10
        pitch_z = max(0.90, sd + 0.50)                               # ASR A1.8 row aisle
        z = max(2.3, min(1.5 * img_w, D * 0.5)) if disp is not None else 2.3
        margin = 0.65 + sw / 2
        n = 0
        # parallel rows, every chair facing the front wall (the display) — angling
        # each seat at the screen point makes edge chairs sliver-collide
        fx2, fz2 = _chair_forward_xz(chairs[0])
        row_yaw = 180.0 - math.degrees(math.atan2(fx2, fz2))
        while z < D - 0.6 and n < len(chairs):
            # centre each row — INCLUDING a partial last row — on the display axis
            n_fit = max(1, int((W - 2 * margin) / pitch_x) + 1)
            row_count = min(n_fit, len(chairs) - n)
            span = (row_count - 1) * pitch_x
            x = min(max(disp_cx - span / 2, margin), max(margin, W - margin - span))
            slots = 0
            while x < W - margin + 1e-6 and slots < row_count and n < len(chairs):
                if _rect_free(x, z, sw, sd):
                    c = chairs[n]
                    _put(c, x, z, row_yaw)
                    c["anchor"] = {"to": disp["id"] if disp else "front_wall",
                                   "relation": "audience_row"}
                    consumed.add(c["id"])
                    n += 1
                x += pitch_x
                slots += 1
            z += pitch_z
    return pos, keep, consumed


def _petal_radius(pw, pdep, kid_max, n_eff):
    """Ring radius for 'beside' petals around a pw×pdep parent: clear of the
    parent on its LONG axis plus breathing room, and wide enough that adjacent
    petals (chord = 2r·sin(pi/n)) never touch each other."""
    r = max(pw, pdep) / 2 + kid_max / 2 + 0.12
    if n_eff > 1:
        r = max(r, (kid_max + 0.06) / (2 * math.sin(math.pi / n_eff)))
    return r


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

    def _clamp_in_room(px, pz, obj, rot_deg):
        """Hard guarantee: an anchored child's footprint never leaves the room."""
        w = float(obj["dimensions"]["width"]); d = float(obj["dimensions"]["depth"])
        if round(float(rot_deg) / 90) % 2 == 1:
            w, d = d, w
        hw, hd = min(w / 2, cw / 2), min(d / 2, ch / 2)
        return min(max(px, hw), cw - hw), min(max(pz, hd), ch - hd)

    direct = {}
    for o in objects:
        a = o.get("anchor")
        if a:
            direct.setdefault(a["to"], []).append(o)
    # presentation halls: the row engine claims display/lectern/projector/rows
    # BEFORE the solve (user rules: rows face + centre on the display, viewing
    # distance, aimed ceiling projector) — runs after `direct` so the anchor
    # tags it writes are report-only, never re-placed
    pres_pos, pres_keep, pres_consumed = {}, [], set()
    if (room.get("type") or "").strip() == "presentation":
        pres_pos, pres_keep, pres_consumed = _presentation_prepass(room, objects)

    # SAFETY ACCESS (ASR — user rule, 'very important'): extinguisher and
    # first-aid cabinet mount on the wall with a PERMANENTLY CLEAR 0.90 m
    # access strip in front — no bookshelf may block them at any density.
    SAFETY_H = {"fire_extinguisher": 1.00, "first_aid_cabinet": 1.35}
    safety_spans = {"back": [], "left": []}
    _safety_items = [x for x in objects if x.get("category") in SAFETY_H
                     and not x.get("anchor") and x["id"] not in pres_consumed]
    for k, o in enumerate(_safety_items):
        sw = float(o["dimensions"]["width"]); sd = float(o["dimensions"]["depth"])
        slot = [(cw * 0.30, "back"), (cw * 0.72, "back"), (ch * 0.5, "left")][k % 3]
        c0, wall = slot
        if wall == "back":
            sx, sz, srot = min(max(c0, 0.4), cw - 0.4), 0.10 + sd / 2, 0
            pres_keep.append({"x": sx - 0.45, "z": 0.0, "width": 0.90,
                              "depth": 0.90, "kind": "safety_access"})
            safety_spans["back"].append((sx - sw / 2 - 0.1, sx + sw / 2 + 0.1))
        else:
            sx, sz, srot = 0.10 + sd / 2, min(max(c0, 0.4), ch - 0.4), 90
            pres_keep.append({"x": 0.0, "z": sz - 0.45, "width": 0.90,
                              "depth": 0.90, "kind": "safety_access"})
            safety_spans["left"].append((sz - sw / 2 - 0.1, sz + sw / 2 + 0.1))
        pres_pos[o["id"]] = {"id": o["id"], "position": [sx, 0.0, sz],
                             "rotation": [0, srot, 0],
                             "elevation": SAFETY_H[o["category"]], "placed": True}
        pres_consumed.add(o["id"])
        o["anchor"] = {"to": "wall", "relation": "mounted_on"}

    # ARMCHAIR ROW CLUSTER (user rule): armchairs sit IN A ROW — two side by
    # side facing the same way; four as two opposed pairs facing each other,
    # side table between (plant on it). Placed anywhere a legal gap exists;
    # the solver's clearances keep it off the walkways.
    _arm_free = [o for o in objects if o.get("category") == "armchair"
                 and not o.get("anchor") and o["id"] not in pres_consumed]
    arm_cluster = None
    if len(_arm_free) >= 2:
        _arms = _arm_free[:4]
        _aw = max(float(a["dimensions"]["width"]) for a in _arms)
        _ad = max(float(a["dimensions"]["depth"]) for a in _arms)
        _st = next((o for o in objects if o.get("category") == "side_table"
                    and not o.get("anchor") and o["id"] not in pres_consumed), None)
        _rows = 1 if len(_arms) <= 2 else 2
        _per_row = 2
        _row_w = _per_row * _aw + 0.15
        _gap = 1.15 if _rows == 2 else 0.0
        _stw = float(_st["dimensions"]["width"]) if _st else 0.0
        _bw = _row_w + ((_stw + 0.15) if (_st and _rows == 1) else 0.0)
        _bd = _rows * _ad + _gap
        arm_cluster = {"arms": _arms, "st": _st, "aw": _aw, "ad": _ad,
                       "rows": _rows, "row_w": _row_w, "gap": _gap, "stw": _stw}
        for a in _arms:
            pres_consumed.add(a["id"])
        if _st:
            pres_consumed.add(_st["id"])
    # wall-mounted decor (clock, picture frame, mirror, tv) never stands on the
    # floor — excluded from the solve, mounted on a wall afterwards
    wall_items = [o for o in objects if not o.get("anchor") and o["id"] not in pres_consumed
                  and rule_packs.archetype_of(o.get("category", ""), o.get("dimensions")) == "wall_mounted"]
    wall_ids = {o["id"] for o in wall_items}
    free = [o for o in objects if not o.get("anchor")
            and o["id"] not in wall_ids and o["id"] not in pres_consumed]

    # Reserve each group's full footprint in the solve: a desk's in-front chair and
    # a parent's beside-child expand its solver box, so groups can't collide.
    solver_objs, meta = [], {}
    for o in free:
        w = float(o["dimensions"]["width"]); d = float(o["dimensions"]["depth"])
        extra_d = 0.0; extra_w = 0.0; front_w = w; beside_n = 0; beside_max = 0.0
        for c in direct.get(o["id"], []):
            rel = c["anchor"].get("relation", "in_front")
            cwd = float(c["dimensions"]["width"]); cdd = float(c["dimensions"]["depth"])
            if rel == "in_front":
                extra_d = max(extra_d, GAP + cdd); front_w = max(front_w, cwd)
            elif rel == "beside":
                extra_w += GAP + cwd
                beside_n += 1
                beside_max = max(beside_max, cwd, cdd)
        entry = {"id": o["id"], "width": max(w, front_w) + extra_w,
                 "depth": d + extra_d, "category": o.get("category", "")}
        if beside_n >= 2:
            # the petal ring is RADIAL — reserve its full circumscribing square,
            # not a widened strip, or chairs above/below the table escape the
            # box and collide with the next table's ring (must mirror the petal
            # pass radius formula, including the chord spread for many kids)
            n_eff = 2 * (beside_n - 1) if extra_d > 0 and beside_n > 1 else beside_n
            ring_r = _petal_radius(w, d, beside_max, n_eff)
            side = 2 * (ring_r + beside_max / 2)
            entry["width"] = max(max(w, front_w), side)
            entry["depth"] = max(d + extra_d, side)
            entry["prefer"] = "center"     # a stool-ringed table is social — keep it open
        elif o.get("category") == "planter":
            entry["prefer"] = "corner"     # greenery lives in corners / by the glazing,
                                           # never in the middle of a room (user rule)
        solver_objs.append(entry)
        meta[o["id"]] = {"w": w, "d": d, "extra_d": extra_d}

    # columns/semi-walls + door keep-clear zones + row-engine floor items +
    # safety access strips become fixed solver keep-outs
    keepouts = list(room.get("obstacles", [])) + list(room.get("doors", [])) + pres_keep
    if arm_cluster:
        solver_objs.append({"id": "_armcluster", "category": "armchair",
                            "width": arm_cluster["row_w"]
                            + ((arm_cluster["stw"] + 0.15) if (arm_cluster["st"] and arm_cluster["rows"] == 1) else 0.0)
                            + 0.10,
                            "depth": arm_cluster["rows"] * arm_cluster["ad"]
                            + arm_cluster["gap"] + 0.10})
    extras = {"unplaced": [], "circulation": None, "diagnostics": None, "zones": {}}
    try:
        import spatial_layout
        res = spatial_layout.layout_room(room, solver_objs, obstacles=keepouts)
        placements = res["placements"]
        extras["unplaced"] = res.get("unplaced", [])
        extras["circulation"] = res.get("circulation")
        extras["diagnostics"] = res.get("diagnostics")
        extras["zones"] = res.get("zones", {})
        # all placed -> real solve; any placed=False -> overpacked (won't fit)
        solver = "ortools-cpsat" if all(p.get("placed", True) for p in placements) \
            else "infeasible-overpacked"
    except Exception as exc:
        print(f"[build_room_scene] solver unavailable ({exc}); grid fallback", file=sys.stderr)
        placements = _grid_fallback(room, solver_objs)
        solver = "grid-fallback"
    box = {p["id"]: p for p in placements}
    pos = {}
    pos.update(pres_pos)     # row-engine placements are final (merged first so
                             # anchored children — flipchart by lectern — resolve)

    def _face(child, px, pz, ax, az):
        target = math.degrees(math.atan2(ax - px, az - pz))   # child -> anchor
        if "chair" in child.get("category", ""):
            fx, fz = _chair_forward_xz(child)
            return target - math.degrees(math.atan2(fx, fz))  # seat-front -> anchor
        return target

    gaze = None            # where a seated person looks (drives clock placement)
    for o in free:
        b = box.get(o["id"])
        if b is None or not b.get("placed", True) or not b.get("position"):
            continue        # honest gate (A4): unplaced items are reported, never dumped
        m = meta[o["id"]]
        bx, _, bz = b["position"]
        rot = (b.get("rotation") or [0, 0, 0])[1]
        # a LONE screen (monitor/laptop with no desk) must still face where a
        # person would be — turn it toward the open room, never toward the wall
        if o.get("category") in _SCREEN_FLIP and not direct.get(o["id"]):
            dxc, dzc = cx - bx, cz - bz
            if abs(dxc) > 1e-6 or abs(dzc) > 1e-6:
                rot = math.degrees(math.atan2(-dxc, -dzc))   # screen (-Z local) -> room centre
        # the solver decides the facing now (A6): its front vector points where the
        # object's users stand — the reserved chair space sits on that side
        fx, fz = b.get("front") or (0.0, 1.0)
        rx_, rz_ = fz, -fx                                  # right-hand perpendicular
        # anchor (parent) sits at the BACK part of the reserved group box
        ax, az = bx - fx * m["extra_d"] / 2.0, bz - fz * m["extra_d"] / 2.0
        pos[o["id"]] = {"id": o["id"], "position": [ax, 0.0, az],
                        "rotation": [0, rot, 0], "placed": True}
        if gaze is None and any("chair" in c.get("category", "") for c in direct.get(o["id"], [])):
            gaze = {"fx": fx, "fz": fz, "x": ax, "z": az}   # the person faces the desk's back wall
        for c in direct.get(o["id"], []):
            rel = c["anchor"].get("relation", "in_front")
            cdd = float(c["dimensions"]["depth"]); cwd = float(c["dimensions"]["width"])
            if rel == "on_top":
                # the offset is in the PARENT's local frame — rotate it with the desk,
                # or a 90°-rotated desk sends its laptop/lamp off the surface (and the room)
                ox, oz = (c["anchor"].get("offset", [0.0, 0.0]) + [0.0, 0.0])[:2]
                wox = float(ox) * rx_ + float(oz) * fx
                woz = float(ox) * rz_ + float(oz) * fz
                px, pz = _clamp_in_room(ax + wox, az + woz, c, rot)
                crot = rot + _SCREEN_FLIP.get(c.get("category", ""), 0.0)   # screen -> chair
                pos[c["id"]] = {"id": c["id"], "position": [px, 0.0, pz],
                                "rotation": [0, crot, 0],
                                "elevation": float(o["dimensions"]["height"]), "placed": True}
            elif rel == "beside":
                off = m["w"] / 2 + cwd / 2 + 0.1
                px, pz = _clamp_in_room(ax + rx_ * off, az + rz_ * off, c, rot)
                pos[c["id"]] = {"id": c["id"], "position": [px, 0.0, pz],
                                "rotation": [0, rot, 0], "placed": True}
            else:  # in_front — on the solver's front side, seat facing the anchor
                off = m["d"] / 2 + GAP + cdd / 2
                px, pz = ax + fx * off, az + fz * off
                pos[c["id"]] = {"id": c["id"], "position": [px, 0.0, pz],
                                "rotation": [0, _face(c, px, pz, ax, az), 0], "placed": True}

    # ---- armchair ROW cluster: rows facing each other, side table between --
    if arm_cluster:
        b = box.get("_armcluster")
        if b and b.get("placed", True) and b.get("position"):
            bx, _, bz = b["position"]
            brot = (b.get("rotation") or [0, 0, 0])[1]
            fx, fz = b.get("front") or (0.0, 1.0)
            rx_, rz_ = fz, -fx
            arms, st = arm_cluster["arms"], arm_cluster["st"]
            aw, ad = arm_cluster["aw"], arm_cluster["ad"]
            rows, gap = arm_cluster["rows"], arm_cluster["gap"]

            def _put_arm(o, lx, lz, face):
                wx, wz = bx + rx_ * lx + fx * lz, bz + rz_ * lx + fz * lz
                fxc, fzc = _chair_forward_xz(o)
                yaw = (math.degrees(math.atan2(face[0], face[1]))
                       - math.degrees(math.atan2(fxc, fzc)))
                pos[o["id"]] = {"id": o["id"], "position": [wx, 0.0, wz],
                                "rotation": [0, yaw, 0], "placed": True}
            xs = [-(aw + 0.15) / 2, (aw + 0.15) / 2]
            if rows == 1:
                shift = -(arm_cluster["stw"] + 0.15) / 2 if st else 0.0
                for i, a in enumerate(arms[:2]):
                    _put_arm(a, xs[i] + shift, 0.0, (fx, fz))    # same direction
                if st:
                    lx = arm_cluster["row_w"] / 2 + arm_cluster["stw"] / 2 + 0.1 + shift
                    pos[st["id"]] = {"id": st["id"],
                                     "position": [bx + rx_ * lx, 0.0, bz + rz_ * lx],
                                     "rotation": [0, brot, 0], "placed": True}
            else:
                zoff = (gap + ad) / 2
                for i, a in enumerate(arms[:2]):
                    _put_arm(a, xs[i], -zoff, (fx, fz))           # pair A ...
                for i, a in enumerate(arms[2:4]):
                    _put_arm(a, xs[i], zoff, (-fx, -fz))          # ... faces pair B
                if st:
                    pos[st["id"]] = {"id": st["id"], "position": [bx, 0.0, bz],
                                     "rotation": [0, brot, 0], "placed": True}

    # nested children (e.g. stool beside coffee-table) — place after their parent
    for o in [x for x in objects if x.get("anchor") and x["id"] not in pos]:
        a = o["anchor"]; ref = pos.get(a["to"])
        if ref is None:
            continue
        rx, _, rz = ref["position"]; rrot = (ref.get("rotation") or [0, 0, 0])[1]
        # parent's local frame (rotates offsets/beside placement with the parent)
        fx2 = math.sin(math.radians(rrot)); fz2 = math.cos(math.radians(rrot))
        rx2, rz2 = fz2, -fx2
        ad = by_id[a["to"]]["dimensions"]; od = o["dimensions"]
        rel = a.get("relation", "in_front")
        if rel == "on_top":
            ox, oz = (a.get("offset", [0.0, 0.0]) + [0.0, 0.0])[:2]
            wox = float(ox) * rx2 + float(oz) * fx2
            woz = float(ox) * rz2 + float(oz) * fz2
            px, pz = _clamp_in_room(rx + wox, rz + woz, o, rrot)
            crot = rrot + _SCREEN_FLIP.get(o.get("category", ""), 0.0)      # screen -> chair
            pos[o["id"]] = {"id": o["id"], "position": [px, 0.0, pz],
                            "rotation": [0, crot, 0], "elevation": float(ad["height"]), "placed": True}
        elif rel == "beside":
            off = float(ad["width"]) / 2 + float(od["width"]) / 2 + 0.1
            px, pz = _clamp_in_room(rx + rx2 * off, rz + rz2 * off, o, rrot)
            pos[o["id"]] = {"id": o["id"], "position": [px, 0.0, pz],
                            "rotation": [0, rrot, 0], "placed": True}
        else:
            off = float(ad["depth"]) / 2 + float(od["depth"]) / 2 + GAP
            pos[o["id"]] = {"id": o["id"], "position": [rx, 0.0, rz + off],
                            "rotation": [0, _face(o, rx, rz + off, rx, rz), 0], "placed": True}

    # ---- petal pass: SEVERAL 'beside' children of one parent fan around it
    # radially (2 opposite, 3 at 120°, 4 at 90°...), each facing the parent —
    # instead of stacking on a single side offset.
    from collections import defaultdict
    beside_groups = defaultdict(list)
    for o in objects:
        a = o.get("anchor")
        if a and a.get("relation") == "beside" and o["id"] in pos and a["to"] in pos:
            beside_groups[a["to"]].append(o)
    for parent_id, kids in beside_groups.items():
        if len(kids) < 2:
            continue
        par = pos[parent_id]
        pd = by_id[parent_id]["dimensions"]
        ax_, az_ = par["position"][0], par["position"][2]
        base = math.radians((par.get("rotation") or [0, 0, 0])[1])   # start at the front
        # a parent with an in_front child (desk + chair) has a PERSON at its
        # front — fan the beside kids over the sides/back arc only, or the
        # first petal lands exactly on the chair. Same when the parent ITSELF
        # is anchored in_front of something (a coffee table faces its sofa):
        # its front sector holds the sofa.
        occupied_front = (any(c.get("anchor", {}).get("relation", "in_front") == "in_front"
                              for c in direct.get(parent_id, []))
                          or (by_id[parent_id].get("anchor") or {}).get("relation") == "in_front")
        kid_max = max(math.hypot(float(c["dimensions"]["width"]),
                                 float(c["dimensions"]["depth"])) for c in kids)
        # a half-arc fan spaces petals like a full circle of 2(n-1) — same chord
        n_eff = 2 * (len(kids) - 1) if occupied_front and len(kids) > 1 else len(kids)
        r = _petal_radius(float(pd["width"]), float(pd["depth"]), kid_max, n_eff)
        for k, c in enumerate(kids):
            if occupied_front:
                ang = base + math.radians(90 + 180 * k / max(1, len(kids) - 1))
            else:
                ang = base + 2 * math.pi * k / len(kids)
            px_, pz_ = ax_ + math.sin(ang) * r, az_ + math.cos(ang) * r
            px_, pz_ = _clamp_in_room(px_, pz_, c, 0)
            pos[c["id"]] = {"id": c["id"], "position": [px_, 0.0, pz_],
                            "rotation": [0, _face(c, px_, pz_, ax_, az_), 0], "placed": True}

    # ---- wall-mount pass: decor hangs ON the wall at human heights — the
    # picture frame at eye level, the CLOCK high on the wall the seated person
    # faces (opposite the chair), the mirror at face height. Spans avoid doors
    # and each other. Only the two rendered walls (back z=0, left x=0) are used.
    if wall_items:
        WALL_T = 0.08
        MOUNT_H = {"clock": 2.05, "picture_frame": 1.55, "mirror": 1.50, "tv": 1.40}
        room_h = float(room.get("height", 3.0))
        spans = {"back": list(safety_spans["back"]),   # safety gear owns its wall strip
                 "left": list(safety_spans["left"])}

        def _blocked(wall, c0, half):
            for (a0, a1) in spans[wall]:
                if c0 + half > a0 and c0 - half < a1:
                    return True
            for dr in room.get("doors", []):
                dx, dz = float(dr["x"]), float(dr["z"])
                dw = float(dr["width"]); dd = float(dr.get("depth", dw))
                if wall == "back" and dz < 0.4 and c0 + half > dx and c0 - half < dx + dw:
                    return True
                if wall == "left" and dx < 0.4 and c0 + half > dz and c0 - half < dz + dd:
                    return True
            return False

        for o in wall_items:
            od = o["dimensions"]
            oh, ow, odp = float(od["height"]), float(od["width"]), float(od["depth"])
            half = ow / 2 + 0.15
            cat = o.get("category", "")
            if cat == "clock" and gaze is not None and gaze["fz"] > 0.3:
                cands = [("back", gaze["x"]), ("back", cw / 2)]     # in the line of sight
            elif cat == "clock" and gaze is not None and gaze["fx"] > 0.3:
                cands = [("left", gaze["z"]), ("left", ch / 2)]
            else:
                base_wall = "left" if cat == "mirror" else "back"
                other = "back" if base_wall == "left" else "left"
                lim_b = cw if base_wall == "back" else ch
                lim_o = cw if other == "back" else ch
                cands = [(base_wall, f * lim_b) for f in (0.5, 0.3, 0.7, 0.18, 0.82)]
                cands += [(other, f * lim_o) for f in (0.5, 0.3, 0.7)]
            chosen = None
            for wall, c0 in cands:
                limit = cw if wall == "back" else ch
                c0 = min(max(c0, half + 0.1), limit - half - 0.1)
                if not _blocked(wall, c0, half):
                    chosen = (wall, c0)
                    break
            if chosen is None:
                wall, c0 = cands[0]
                limit = cw if wall == "back" else ch
                chosen = (wall, min(max(c0, half), limit - half))
            wall, c0 = chosen
            spans[wall].append((c0 - half, c0 + half))
            elev = min(max(MOUNT_H.get(cat, 1.5) - oh / 2, 0.9), room_h - oh - 0.05)
            zoff = WALL_T + odp / 2 + 0.01
            if wall == "back":
                pos[o["id"]] = {"id": o["id"], "position": [c0, 0.0, zoff],
                                "rotation": [0, 0, 0], "elevation": elev, "placed": True}
            else:
                pos[o["id"]] = {"id": o["id"], "position": [zoff, 0.0, c0],
                                "rotation": [0, 90, 0], "elevation": elev, "placed": True}

    # projector — ANY room type (user rule, 'never forget'): never on the floor.
    # With a display in the room (screen, else whiteboard) it hangs from the
    # ceiling at throw distance aimed at it; otherwise ceiling mid-room.
    # Presentation halls were already handled by the row pre-pass (elev 2.2).
    for o in objects:
        if o.get("category") != "projector":
            continue
        p = pos.get(o["id"])
        if p is None or float(p.get("elevation") or 0) > 1.0:
            continue
        disp = next((x for x in objects if x.get("category") == "presentation_screen"
                     and x["id"] in pos), None) \
            or next((x for x in objects if x.get("category") == "whiteboard"
                     and x["id"] in pos), None)
        if disp is not None:
            dp = pos[disp["id"]]
            hx, hz = dp["position"][0], dp["position"][2]
            drot = math.radians((dp.get("rotation") or [0, 0, 0])[1])
            nx, nz = math.sin(drot), math.cos(drot)      # wall normal, into the room
            throw = min(3.5, max(1.5, 1.2 * float(disp["dimensions"]["width"])))
            px = min(max(hx + nx * throw, 0.4), cw - 0.4)
            pz = min(max(hz + nz * throw, 0.4), ch - 0.4)
            yaw = math.degrees(math.atan2(hx - px, hz - pz))
            o["anchor"] = o.get("anchor") or {"to": disp["id"], "relation": "throws_onto"}
        else:
            px, pz, yaw = cx, cz, 0.0
            o["anchor"] = o.get("anchor") or {"to": "ceiling", "relation": "ceiling_mount"}
        pos[o["id"]] = {"id": o["id"], "position": [px, 0.0, pz],
                        "rotation": [0, yaw, 0], "elevation": 2.2, "placed": True}

    # dependency realism (user rule): service items exist FOR the furniture
    # they serve. A room that ends up with NO work/dining surface keeps at
    # most one waste bin (door duty) and no partitions — refused, not forced.
    def _has(cat):
        return any(o.get("category") == cat and (pos.get(o["id"]) or {}).get("placed")
                   for o in objects)
    if not (_has("desk") or _has("table")):
        kept_bin = False
        for o in objects:
            c = o.get("category")
            p = pos.get(o["id"])
            if not p or not p.get("placed"):
                continue
            if c == "waste_bin":
                if kept_bin:
                    p["placed"] = False
                    p["position"] = None
                    extras["unplaced"].append(o["id"])
                kept_bin = True
            elif c == "partition":
                p["placed"] = False
                p["position"] = None
                extras["unplaced"].append(o["id"])
    return pos, solver, extras


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
    parts = {
        "room-floor": (_coloured(floor, [0.82, 0.80, 0.76]), "Floor", "IfcSlab"),
        "room-wall-back": (_coloured(wall_back, [0.90, 0.90, 0.88]), "Wall (back)", "IfcWall"),
        "room-wall-left": (_coloured(wall_left, [0.90, 0.90, 0.88]), "Wall (left)", "IfcWall"),
    }
    # columns / semi-walls (corner-origin rectangles, matching the solver keep-outs)
    for i, ob in enumerate(room.get("obstacles", [])):
        ox, oz = float(ob["x"]), float(ob["z"])
        ow, od = float(ob["width"]), float(ob["depth"])
        kind = ob.get("kind", "column")
        oh = h if kind == "column" else min(h, float(ob.get("height", 1.2)))
        box = trimesh.creation.box(extents=[ow, oh, od])
        box.apply_translation([ox + ow / 2, oh / 2, oz + od / 2])
        parts[f"room-obstacle-{i}"] = (_coloured(box, [0.55, 0.55, 0.58]),
                                       "Column" if kind == "column" else "Partition",
                                       "IfcColumn" if kind == "column" else "IfcWall")
    # door keep-clear zones — thin blue floor patch (never built on)
    for i, dr in enumerate(room.get("doors", [])):
        dx, dz = float(dr["x"]), float(dr["z"])
        dw, dd = float(dr["width"]), float(dr["depth"])
        patch = trimesh.creation.box(extents=[dw, 0.02, dd])
        patch.apply_translation([dx + dw / 2, 0.012, dz + dd / 2])
        parts[f"room-door-{i}"] = (_coloured(patch, [0.35, 0.6, 0.95]),
                                   "Door clearance", "IfcDoor")
    return parts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build(spec: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    room = spec["room"]
    objects = spec["objects"]

    pos_by_id, solver, extras = _resolve_layout(room, objects)

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
        anchor = obj.get("anchor") or {}
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
            "elevation": round(float(p.get("elevation", 0.0)), 3),
            "source": obj.get("source", ""),
            "license": obj.get("license", ""),
            # functional relationship (A6) — persisted into the IFC by build_room_ifc
            "anchor_to": anchor.get("to"),
            "relation": anchor.get("relation"),
        })

    # Export combined GLB
    scene = trimesh.Scene(geometry=geometry)
    glb_path = out_dir / "scene.glb"
    scene.export(str(glb_path))

    # MetaModel (xeokit)
    (out_dir / "metamodel.json").write_text(
        json.dumps({"metaObjects": meta_objects}, indent=2), encoding="utf-8")

    # A4 — honest per-item reporting: which of the user's picks could NOT be
    # placed (an unplaced parent takes its anchored children down with it)
    unplaced_ids = set(extras.get("unplaced") or [])
    for o in objects:
        a = o.get("anchor")
        if a and a.get("to") in unplaced_ids:
            unplaced_ids.add(o["id"])
    unplaced_items = [{"id": o["id"], "name": o.get("name", o["id"]),
                       "category": o.get("category", "")}
                      for o in objects if o["id"] in unplaced_ids]

    # Schedule JSON + CSV (zones ride along for the 2D floor-plan editor)
    (out_dir / "schedule.json").write_text(
        json.dumps({"room": room, "solver": solver, "items": schedule,
                    "zones": extras.get("zones", {}),
                    "unplaced": unplaced_items,
                    "circulation": extras.get("circulation"),
                    "diagnostics": extras.get("diagnostics")}, indent=2),
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
        "unplaced": unplaced_items,
        "circulation": extras.get("circulation"),
        "diagnostics": extras.get("diagnostics"),
        "outputs": ["scene.glb", "metamodel.json", "schedule.json", "schedule.csv"],
    }


def rebuild_from_schedule(spec: dict, out_dir: Path) -> dict:
    """Re-assemble scene.glb from the CURRENT schedule.json positions (after manual
    2D edits) without re-running the solver. The spec supplies each object's mesh
    (glb path / colour); the schedule supplies x/z/rotation/elevation."""
    sched = json.loads((out_dir / "schedule.json").read_text(encoding="utf-8"))
    room = sched["room"]
    by_id = {o["id"]: o for o in spec["objects"]}

    geometry = {}
    meta_objects = [{"id": "room", "name": room.get("name", "Room"),
                     "type": "IfcSpace", "parent": None}]
    for node_id, (mesh, name, ifc) in _room_shell(room).items():
        geometry[node_id] = mesh
        meta_objects.append({"id": node_id, "name": name, "type": ifc, "parent": "room"})
    for it in sched["items"]:
        obj = by_id.get(it["id"])
        if obj is None:
            continue
        placed = _place(_object_mesh(obj), [it["x"], 0.0, it["z"]],
                        it.get("rotation_deg", 0), it.get("elevation", 0.0))
        geometry[it["id"]] = placed
        meta_objects.append({"id": it["id"], "name": it.get("name", it["id"]),
                             "type": it.get("ifc_class", "IfcFurnishingElement"), "parent": "room"})

    scene = trimesh.Scene(geometry=geometry)
    glb_path = out_dir / "scene.glb"
    scene.export(str(glb_path))
    (out_dir / "metamodel.json").write_text(
        json.dumps({"metaObjects": meta_objects}, indent=2), encoding="utf-8")
    return {"success": True, "glb_bytes": glb_path.stat().st_size}


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
