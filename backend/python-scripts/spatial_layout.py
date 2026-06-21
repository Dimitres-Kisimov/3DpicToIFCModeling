"""
Sprint 5 — Spatial Layout Engine
Uses OR-Tools CP-SAT solver to place furniture objects in a room without overlap,
respecting clearances, wall proximity, and ergonomic constraints.

Room coordinate system: X=width, Z=depth, Y=up (metres)
All furniture footprints are rectangles (AABB projected on XZ plane).

Usage:
  python spatial_layout.py <room_json> [<objects_json>]

  room_json:    {"width": 8.0, "depth": 6.0, "height": 3.0}
  objects_json: [{"id":"chair1","width":0.6,"depth":0.6,"clearance":0.5}, ...]

OR-Tools install: pip install ortools
"""

import sys
import json
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit

# Clearance presets by object category (metres)
# Small buffers only: the chair/circulation space is reserved separately via group
# footprints, and wall-affinity keeps the room centre open — so these are just
# minimum gaps between neighbouring items, not full circulation envelopes.
CLEARANCE_PRESETS = {
    "chair":             0.10,
    "office_chair":      0.10,
    "desk":              0.15,
    "conference_table":  0.30,
    "table":             0.15,
    "coffee_table":      0.15,
    "side_table":        0.10,
    "sofa":              0.20,
    "stool":             0.10,
    "bookshelf":         0.10,
    "cabinet":           0.20,   # door/drawer swing
    "filing_cabinet":    0.20,
    "printer":           0.15,
    "lamp":              0.10,
    "monitor":           0.05,
    "plant":             0.10,
    "default":           0.15,
}


def _get_clearance(obj):
    return obj.get("clearance") or CLEARANCE_PRESETS.get(obj.get("category", ""), CLEARANCE_PRESETS["default"])


def _solve_layout_ortools(room, objects, obstacles=None):
    """
    CP-SAT integer programming placement.
    Discretises the room into a 10 cm grid.
    obstacles: fixed keep-out rectangles [{x, z, width, depth}] (metres) — columns,
    semi-walls, and door keep-clear zones. Nothing may overlap them.
    Returns list of {id, x, z, rotation} placements.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        error_exit("OR-Tools not installed. Run: pip install ortools")

    SCALE = 10  # 1 unit = 10 cm
    room_w = int(room["width"] * SCALE)
    room_d = int(room["depth"] * SCALE)
    WALL_MARGIN = 2  # 20 cm from walls minimum

    model = cp_model.CpModel()
    placements = []

    for obj in objects:
        c = _get_clearance(obj)
        fw = int((obj["width"]  + c * 2) * SCALE)
        fd = int((obj["depth"]  + c * 2) * SCALE)

        # Only allow 0° and 90° rotation
        # rotation=0: footprint fw×fd, rotation=1: fd×fw
        rot = model.NewBoolVar(f"rot_{obj['id']}")

        # x,z position of the padded bounding box origin
        max_x0 = model.NewIntVar(WALL_MARGIN, room_w - fw - WALL_MARGIN, f"x0_r0_{obj['id']}")
        max_x1 = model.NewIntVar(WALL_MARGIN, room_w - fd - WALL_MARGIN, f"x0_r1_{obj['id']}")
        max_z0 = model.NewIntVar(WALL_MARGIN, room_d - fd - WALL_MARGIN, f"z0_r0_{obj['id']}")
        max_z1 = model.NewIntVar(WALL_MARGIN, room_d - fw - WALL_MARGIN, f"z0_r1_{obj['id']}")

        x = model.NewIntVar(WALL_MARGIN, room_w, f"x_{obj['id']}")
        z = model.NewIntVar(WALL_MARGIN, room_d, f"z_{obj['id']}")
        w = model.NewIntVar(1, room_w, f"w_{obj['id']}")
        d = model.NewIntVar(1, room_d, f"d_{obj['id']}")

        # x = rot?max_x1:max_x0, etc.
        model.Add(x == max_x0).OnlyEnforceIf(rot.Not())
        model.Add(x == max_x1).OnlyEnforceIf(rot)
        model.Add(z == max_z0).OnlyEnforceIf(rot.Not())
        model.Add(z == max_z1).OnlyEnforceIf(rot)
        model.Add(w == fw).OnlyEnforceIf(rot.Not())
        model.Add(w == fd).OnlyEnforceIf(rot)
        model.Add(d == fd).OnlyEnforceIf(rot.Not())
        model.Add(d == fw).OnlyEnforceIf(rot)

        # ortools 9.15 requires the interval end to be a single affine var,
        # not a sum expression — bind explicit end vars.
        ex = model.NewIntVar(WALL_MARGIN, room_w, f"ex_{obj['id']}")
        ez = model.NewIntVar(WALL_MARGIN, room_d, f"ez_{obj['id']}")
        model.Add(ex == x + w)
        model.Add(ez == z + d)
        ix = model.NewIntervalVar(x, w, ex, f"ix_{obj['id']}")
        iz = model.NewIntervalVar(z, d, ez, f"iz_{obj['id']}")

        placements.append({"obj": obj, "x": x, "z": z, "w": w, "d": d, "rot": rot, "ix": ix, "iz": iz})

    # Fixed keep-out rectangles: columns, semi-walls, and door keep-clear zones.
    ob_ix, ob_iz = [], []
    for k, ob in enumerate(obstacles or []):
        ox = max(0, int(float(ob["x"]) * SCALE)); oz = max(0, int(float(ob["z"]) * SCALE))
        ow = max(1, int(float(ob["width"]) * SCALE)); od = max(1, int(float(ob["depth"]) * SCALE))
        ob_ix.append(model.NewFixedSizeIntervalVar(ox, ow, f"obx_{k}"))
        ob_iz.append(model.NewFixedSizeIntervalVar(oz, od, f"obz_{k}"))

    # No-overlap across all furniture pairs AND fixed obstacles
    model.AddNoOverlap2D(
        [p["ix"] for p in placements] + ob_ix,
        [p["iz"] for p in placements] + ob_iz,
    )

    # Ergonomic perimeter affinity: pull large/storage items toward the walls,
    # keeping the room centre open for circulation.
    PERIMETER = {"desk", "cabinet", "filing_cabinet", "storage_cabinet",
                 "bookshelf", "sofa", "side_table"}
    wall_terms = []
    for p in placements:
        if p["obj"].get("category") in PERIMETER:
            x, z, w, d = p["x"], p["z"], p["w"], p["d"]
            dr = model.NewIntVar(0, room_w, f"dr_{p['obj']['id']}")
            db = model.NewIntVar(0, room_d, f"db_{p['obj']['id']}")
            model.Add(dr == room_w - x - w)
            model.Add(db == room_d - z - d)
            md = model.NewIntVar(0, max(room_w, room_d), f"wall_{p['obj']['id']}")
            model.AddMinEquality(md, [x, dr, z, db])
            wall_terms.append(md)
    if wall_terms:
        model.Minimize(sum(wall_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        log("CP-SAT could not find feasible layout — returning stacked default", "warn")
        return _fallback_stack_layout(room, objects)

    result = []
    for p in placements:
        obj = p["obj"]
        x_val = solver.Value(p["x"]) / SCALE
        z_val = solver.Value(p["z"]) / SCALE
        rot_val = solver.Value(p["rot"])
        c = _get_clearance(obj)
        # Centre position (remove clearance padding)
        cx = x_val + c + obj["width"]  / 2
        cz = z_val + c + obj["depth"]  / 2
        result.append({
            "id": obj["id"],
            "position": [round(cx, 3), 0.0, round(cz, 3)],
            "rotation": [0, 90 * rot_val, 0],
            "placed": True,
        })
        log(f"Placed {obj['id']} at ({cx:.2f}, 0, {cz:.2f}) rot={90*rot_val}°", "info")

    return result


def _fallback_stack_layout(room, objects):
    """Simple row layout when solver finds no feasible solution."""
    x, z = 0.5, 0.5
    result = []
    max_z = room.get("depth", 6.0) - 0.5
    for obj in objects:
        result.append({
            "id": obj["id"],
            "position": [round(x, 3), 0.0, round(z, 3)],
            "rotation": [0, 0, 0],
            "placed": False,
        })
        z += obj.get("depth", 0.6) + _get_clearance(obj) * 2 + 0.1
        if z > max_z:
            z = 0.5
            x += 1.5
    return result


def layout_room(room, objects, obstacles=None):
    log(f"Room: {room['width']}m × {room['depth']}m, {len(objects)} objects, "
        f"{len(obstacles or [])} obstacles", "info")
    placements = _solve_layout_ortools(room, objects, obstacles)
    return {
        "room": room,
        "placements": placements,
        "obstacles": obstacles or [],
        "solver": "ortools-cpsat",
        "object_count": len(placements),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        error_exit("Usage: spatial_layout.py <room_json> [objects_json]")

    room = json.loads(sys.argv[1])
    objects = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []

    result = layout_room(room, objects)
    success_exit(result)
