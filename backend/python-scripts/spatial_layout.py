"""
Spatial Layout Engine — people-aware CP-SAT furniture placement (Part 2, A2/A3/A4).

Places furniture in a room so that BOTH the objects and the HUMANS who use them
fit: every object's footprint (plus a neighbour gap) must not overlap anything,
and its archetype's INTERACTION ZONES (legroom at a desk, door swing at a cabinet,
access strips around a bed — from rule_packs.placement_profile) are reserved
rectangles that no footprint or fixed obstacle may invade. Zones may overlap each
other (people share circulation space) but must lie inside the room.

Rotation is 0/90/180/270 so facing can always be satisfied; wall-affine archetypes
(desk/storage/bed/sofa) are pulled BACK-to-wall by an orientation-aware objective.

Placement is OPTIONAL per object (A4): the solver maximises how many of the user's
picks fit with full ergonomics; whatever cannot fit is reported honestly per item
("not enough space"), never dumped at random.

After solving, a circulation check (A3) walks a person through the room on a 10 cm
grid: from each door (or the room's open core) there must be an aisle-wide path to
every object's interaction zone. Unreachable items are reported.

Room coordinate system: X=width, Z=depth, Y=up (metres).

Usage:
  python spatial_layout.py <room_json> [<objects_json>]
"""

import sys
import json
import math
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit
import rule_packs

# Clearance presets by object category (metres) — minimum gaps between neighbours.
# Human interaction space is handled separately by the archetype zones.
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
    "cabinet":           0.20,
    "filing_cabinet":    0.20,
    "printer":           0.15,
    "lamp":              0.10,
    "monitor":           0.05,
    "plant":             0.10,
    "bed":               0.10,
    "default":           0.15,
}

# Legacy wall-affinity hint for categories without a wall-affine archetype. Unknown
# items still fall through to the geometry rule so the solver stays item-agnostic.
_PERIMETER_CATS = {"desk", "cabinet", "filing_cabinet", "storage_cabinet", "bookshelf",
                   "sofa", "side_table", "tv_stand", "wardrobe", "dresser", "bed", "shelf"}

SCALE = 10          # 1 grid unit = 10 cm
WALL_MARGIN = 2     # 20 cm minimum from walls
PLACE_REWARD = 100000   # objective reward per placed object (dominates gap terms)

# world sides, index k = local side rotated by k*90° CCW about Y (+Z -> +X):
# 0 = +Z (north), 1 = +X (east), 2 = -Z (south), 3 = -X (west)
_LOCAL_SIDE_INDEX = {"front": 0, "right": 1, "back": 2, "left": 3}


def _get_clearance(obj):
    """Minimum neighbour gap in metres: explicit > category preset > derived from footprint."""
    if obj.get("clearance"):
        return obj["clearance"]
    cat = obj.get("category", "")
    if cat in CLEARANCE_PRESETS:
        return CLEARANCE_PRESETS[cat]
    reach = max(float(obj.get("width", 0.5)), float(obj.get("depth", 0.5)))
    return round(min(0.35, max(0.10, 0.10 + 0.12 * (reach - 0.5))), 3)


def _is_perimeter(obj):
    """Wall-affinity for items whose archetype gives no wall rule: tall pieces and
    elongated footprints have a natural 'back' and hug walls; low square ones don't."""
    if obj.get("category") in _PERIMETER_CATS:
        return True
    w, d = float(obj.get("width", 0.5)), float(obj.get("depth", 0.5))
    h = float(obj.get("height", 0.0) or 0.0)
    aspect = max(w, d) / max(1e-6, min(w, d))
    return h >= 1.2 or aspect >= 1.6


def _profile(obj):
    """placement_profile for a solver object (dims as h/w/d dict)."""
    return rule_packs.placement_profile(
        obj.get("category", ""),
        {"height": obj.get("height", 0.0), "width": obj.get("width", 0.5),
         "depth": obj.get("depth", 0.5)},
    )


def _solve_layout_ortools(room, objects, obstacles=None):
    """CP-SAT placement on a 10 cm grid. Returns (placements, zones_by_id, unplaced_ids).

    Each placement: {id, position [cx,0,cz] (m), rotation [0,deg,0], placed,
                     rect [x0,z0,w,d] (m, unpadded footprint), front [fx,fz]}.
    zones_by_id: {id: [[x0,z0,w,d], ...]} world interaction-zone rectangles (m).
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        error_exit("OR-Tools not installed. Run: pip install ortools")

    room_w = int(room["width"] * SCALE)
    room_d = int(room["depth"] * SCALE)

    model = cp_model.CpModel()
    placements = []

    # ---- fixed keep-out rectangles (columns, walls, beams, door keep-clear) ----
    # Constrained PAIRWISE against furniture (not via AddNoOverlap2D) so that
    # overlapping fixed elements — a beam inside a wall — can't make the model
    # infeasible on their own (A3b: obstacles arrive labeled, not pre-merged).
    ob_rects = []                    # grid rects (x0, z0, w, d)
    for k, ob in enumerate(obstacles or []):
        ox = max(0, int(float(ob["x"]) * SCALE)); oz = max(0, int(float(ob["z"]) * SCALE))
        ow = max(1, int(float(ob["width"]) * SCALE)); od = max(1, int(float(ob["depth"]) * SCALE))
        ob_rects.append((ox, oz, ow, od))

    # ---- per-object variables ---------------------------------------------------
    for obj in objects:
        oid = obj["id"]
        c = _get_clearance(obj)
        fw = int(round((obj["width"] + c * 2) * SCALE))     # padded footprint at rot 0
        fd = int(round((obj["depth"] + c * 2) * SCALE))
        if fw > room_w - 2 * WALL_MARGIN or fd > room_d - 2 * WALL_MARGIN:
            # can never fit even alone — mark as impossible (forced absent)
            pass

        present = model.NewBoolVar(f"p_{oid}")
        rots = [model.NewBoolVar(f"r{k}_{oid}") for k in range(4)]
        model.AddExactlyOne(rots)

        x = model.NewIntVar(0, room_w, f"x_{oid}")
        z = model.NewIntVar(0, room_d, f"z_{oid}")
        w = model.NewIntVar(1, room_w, f"w_{oid}")
        d = model.NewIntVar(1, room_d, f"d_{oid}")
        ex = model.NewIntVar(0, room_w, f"ex_{oid}")
        ez = model.NewIntVar(0, room_d, f"ez_{oid}")
        model.Add(ex == x + w)
        model.Add(ez == z + d)
        # footprint dims per rotation (0/180 keep w×d; 90/270 swap)
        for k in (0, 2):
            model.Add(w == fw).OnlyEnforceIf(rots[k])
            model.Add(d == fd).OnlyEnforceIf(rots[k])
        for k in (1, 3):
            model.Add(w == fd).OnlyEnforceIf(rots[k])
            model.Add(d == fw).OnlyEnforceIf(rots[k])

        # wall margins: every side keeps WALL_MARGIN — EXCEPT the back side of a
        # wall-affine item, which may touch its wall (only the neighbour clearance
        # remains, so wardrobes/desks sit snug instead of floating 0.4 m out)
        prof = _profile(obj)
        wall_back = prof["wall"] == "back"
        back_base = _LOCAL_SIDE_INDEX["back"]
        for k in range(4):
            back_side = (back_base + k) % 4 if wall_back else -1
            lits = [rots[k], present]
            if back_side != 0:
                model.Add(ez <= room_d - WALL_MARGIN).OnlyEnforceIf(lits)
            if back_side != 1:
                model.Add(ex <= room_w - WALL_MARGIN).OnlyEnforceIf(lits)
            if back_side != 2:
                model.Add(z >= WALL_MARGIN).OnlyEnforceIf(lits)
            if back_side != 3:
                model.Add(x >= WALL_MARGIN).OnlyEnforceIf(lits)
        model.Add(ex <= room_w).OnlyEnforceIf(present)
        model.Add(ez <= room_d).OnlyEnforceIf(present)

        ix = model.NewOptionalIntervalVar(x, w, ex, present, f"ix_{oid}")
        iz = model.NewOptionalIntervalVar(z, d, ez, present, f"iz_{oid}")

        # ---- interaction zones (A2): channelled rectangles that rotate with the object
        zones = []

        def _make_zone(direction, depth_m, active):
            """active: literal that turns this zone on (present itself for required
            zones; a choice literal for either-or groups like bed sides)."""
            q = int(round(depth_m * SCALE))
            if q <= 0:
                return
            zx = model.NewIntVar(0, room_w, f"zx_{direction}_{oid}")
            zz = model.NewIntVar(0, room_d, f"zz_{direction}_{oid}")
            zw = model.NewIntVar(1, room_w, f"zw_{direction}_{oid}")
            zd = model.NewIntVar(1, room_d, f"zd_{direction}_{oid}")
            zex = model.NewIntVar(0, room_w, f"zex_{direction}_{oid}")
            zez = model.NewIntVar(0, room_d, f"zez_{direction}_{oid}")
            model.Add(zex == zx + zw)
            model.Add(zez == zz + zd)
            base = _LOCAL_SIDE_INDEX[direction]
            for k in range(4):
                side = (base + k) % 4       # world side after rotation
                lits = [rots[k], active]
                if side == 0:    # +Z: above the footprint
                    model.Add(zx == x).OnlyEnforceIf(lits)
                    model.Add(zw == w).OnlyEnforceIf(lits)
                    model.Add(zz == ez).OnlyEnforceIf(lits)
                    model.Add(zd == q).OnlyEnforceIf(lits)
                elif side == 1:  # +X: right of the footprint
                    model.Add(zx == ex).OnlyEnforceIf(lits)
                    model.Add(zw == q).OnlyEnforceIf(lits)
                    model.Add(zz == z).OnlyEnforceIf(lits)
                    model.Add(zd == d).OnlyEnforceIf(lits)
                elif side == 2:  # -Z: below
                    model.Add(zx == x).OnlyEnforceIf(lits)
                    model.Add(zw == w).OnlyEnforceIf(lits)
                    model.Add(zez == z).OnlyEnforceIf(lits)
                    model.Add(zd == q).OnlyEnforceIf(lits)
                else:            # -X: left
                    model.Add(zex == x).OnlyEnforceIf(lits)
                    model.Add(zw == q).OnlyEnforceIf(lits)
                    model.Add(zz == z).OnlyEnforceIf(lits)
                    model.Add(zd == d).OnlyEnforceIf(lits)
            # the zone itself must be inside the room — people stand in it
            model.Add(zx >= 0).OnlyEnforceIf(active)
            model.Add(zz >= 0).OnlyEnforceIf(active)
            model.Add(zex <= room_w).OnlyEnforceIf(active)
            model.Add(zez <= room_d).OnlyEnforceIf(active)
            zones.append({"dir": direction, "zx": zx, "zz": zz, "zw": zw, "zd": zd,
                          "zex": zex, "zez": zez, "active": active})

        for direction, depth_m in prof["zones"].items():
            _make_zone(direction, depth_m, present)          # required zone
        if prof.get("zones_any"):
            # at least ONE of the group's zones must be honoured (bed sides)
            choice = []
            for direction, depth_m in prof["zones_any"]:
                lit = model.NewBoolVar(f"zopt_{direction}_{oid}")
                model.AddImplication(lit, present)
                _make_zone(direction, depth_m, lit)
                choice.append(lit)
            if choice:
                model.AddBoolOr(choice).OnlyEnforceIf(present)

        # ---- orientation-aware wall affinity (back edge -> nearest chosen wall)
        wall_gap = None
        if prof["wall"] == "back":
            wall_gap = model.NewIntVar(0, max(room_w, room_d), f"wg_{oid}")
            back_base = _LOCAL_SIDE_INDEX["back"]
            for k in range(4):
                side = (back_base + k) % 4
                lits = [rots[k], present]
                if side == 0:    # back faces +Z wall
                    model.Add(wall_gap == room_d - ez).OnlyEnforceIf(lits)
                elif side == 1:  # +X wall
                    model.Add(wall_gap == room_w - ex).OnlyEnforceIf(lits)
                elif side == 2:  # -Z wall
                    model.Add(wall_gap == z).OnlyEnforceIf(lits)
                else:            # -X wall
                    model.Add(wall_gap == x).OnlyEnforceIf(lits)
            model.Add(wall_gap == 0).OnlyEnforceIf(present.Not())

        placements.append({"obj": obj, "present": present, "rots": rots,
                           "x": x, "z": z, "w": w, "d": d, "ex": ex, "ez": ez,
                           "ix": ix, "iz": iz, "zones": zones, "wall_gap": wall_gap,
                           "clearance": c, "prof": prof})

    # ---- footprint no-overlap (furniture vs furniture) --------------------------
    model.AddNoOverlap2D([p["ix"] for p in placements], [p["iz"] for p in placements])

    # ---- footprints may not sit on fixed obstacles (pairwise) -------------------
    for i, p in enumerate(placements):
        for k, (ox, oz, ow, od) in enumerate(ob_rects):
            b = [model.NewBoolVar(f"fo_{i}_{k}_{t}") for t in range(4)]
            model.Add(p["ex"] <= ox).OnlyEnforceIf(b[0])
            model.Add(p["x"] >= ox + ow).OnlyEnforceIf(b[1])
            model.Add(p["ez"] <= oz).OnlyEnforceIf(b[2])
            model.Add(p["z"] >= oz + od).OnlyEnforceIf(b[3])
            model.AddBoolOr(b).OnlyEnforceIf([p["present"]])

    # ---- zones may not be invaded by ANY footprint or obstacle ------------------
    # (zone-zone overlap is allowed: people share circulation space)
    def _rects_apart(model, ax, aex, az, aez, bx, bex, bz, bez, lits, tag):
        """a strictly left/right/above/below b, reified under lits."""
        b = [model.NewBoolVar(f"{tag}_{i}") for i in range(4)]
        model.Add(aex <= bx).OnlyEnforceIf(b[0])
        model.Add(ax >= bex).OnlyEnforceIf(b[1])
        model.Add(aez <= bz).OnlyEnforceIf(b[2])
        model.Add(az >= bez).OnlyEnforceIf(b[3])
        model.AddBoolOr(b).OnlyEnforceIf(lits)

    for i, p in enumerate(placements):
        for zn, zv in enumerate(p["zones"]):
            # vs every OTHER object's footprint
            for j, q in enumerate(placements):
                if i == j:
                    continue
                _rects_apart(model, zv["zx"], zv["zex"], zv["zz"], zv["zez"],
                             q["x"], q["ex"], q["z"], q["ez"],
                             [zv["active"], q["present"]], f"za_{i}_{zn}_{j}")
            # vs fixed obstacles
            for k, (ox, oz, ow, od) in enumerate(ob_rects):
                b = [model.NewBoolVar(f"zo_{i}_{zn}_{k}_{t}") for t in range(4)]
                model.Add(zv["zex"] <= ox).OnlyEnforceIf(b[0])
                model.Add(zv["zx"] >= ox + ow).OnlyEnforceIf(b[1])
                model.Add(zv["zez"] <= oz).OnlyEnforceIf(b[2])
                model.Add(zv["zz"] >= oz + od).OnlyEnforceIf(b[3])
                model.AddBoolOr(b).OnlyEnforceIf([zv["active"]])

    # ---- objective: place as many as possible, backs to walls, centre open ------
    # Per-item reward is weighted by footprint area and list order, so when space
    # runs out the solver keeps the ESSENTIALS (the bed) over accents (the lamp) —
    # smart_furnish and the user's picks both list important items first.
    gap_terms, place_terms = [], []
    n = len(placements)
    for idx, p in enumerate(placements):
        c = p["clearance"]
        area = int((p["obj"]["width"] + 2 * c) * (p["obj"]["depth"] + 2 * c) * SCALE * SCALE)
        reward = PLACE_REWARD + area // 5 + (n - idx) * 500
        place_terms.append(p["present"] * reward)
        if p["wall_gap"] is not None:
            gap_terms.append(p["wall_gap"])
        elif _is_perimeter(p["obj"]):
            x, z, ex, ez = p["x"], p["z"], p["ex"], p["ez"]
            dr = model.NewIntVar(0, room_w, f"dr_{p['obj']['id']}")
            db = model.NewIntVar(0, room_d, f"db_{p['obj']['id']}")
            model.Add(dr == room_w - ex)
            model.Add(db == room_d - ez)
            md = model.NewIntVar(0, max(room_w, room_d), f"wall_{p['obj']['id']}")
            model.AddMinEquality(md, [x, dr, z, db])
            gap_terms.append(md)
    model.Maximize(sum(place_terms) - sum(gap_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        log("CP-SAT found no layout at all — returning stacked default", "warn")
        return _fallback_stack_layout(room, objects), {}, [o["id"] for o in objects]

    result, zones_by_id, unplaced = [], {}, []
    for p in placements:
        obj = p["obj"]
        if not solver.Value(p["present"]):
            unplaced.append(obj["id"])
            result.append({"id": obj["id"], "position": None, "rotation": [0, 0, 0],
                           "placed": False})
            continue
        x_val, z_val = solver.Value(p["x"]), solver.Value(p["z"])
        w_val, d_val = solver.Value(p["w"]), solver.Value(p["d"])
        k = next(kk for kk in range(4) if solver.Value(p["rots"][kk]))
        c = p["clearance"]
        # rotation-correct centre of the REAL (unpadded) footprint
        cx = (x_val + w_val / 2.0) / SCALE
        cz = (z_val + d_val / 2.0) / SCALE
        theta = math.radians(90 * k)
        front = [round(math.sin(theta), 6), round(math.cos(theta), 6)]
        rw = w_val / SCALE - 2 * c      # unpadded rotated dims
        rd = d_val / SCALE - 2 * c
        result.append({
            "id": obj["id"],
            "position": [round(cx, 3), 0.0, round(cz, 3)],
            "rotation": [0, 90 * k, 0],
            "placed": True,
            "front": front,
            "rect": [round(cx - rw / 2, 3), round(cz - rd / 2, 3), round(rw, 3), round(rd, 3)],
        })
        zrects = []
        for zv in p["zones"]:
            if not solver.Value(zv["active"]):
                continue                      # either-or zone not chosen
            zrects.append([round(solver.Value(zv["zx"]) / SCALE, 3),
                           round(solver.Value(zv["zz"]) / SCALE, 3),
                           round(solver.Value(zv["zw"]) / SCALE, 3),
                           round(solver.Value(zv["zd"]) / SCALE, 3)])
        if zrects:
            zones_by_id[obj["id"]] = zrects
        log(f"Placed {obj['id']} at ({cx:.2f}, 0, {cz:.2f}) rot={90*k}°", "info")

    return result, zones_by_id, unplaced


def _fallback_stack_layout(room, objects):
    """Simple row layout when OR-Tools finds nothing at all (should be rare)."""
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


# ---------------------------------------------------------------------------
# A3 — circulation: a person must be able to WALK from the door(s) to every
# object's interaction zone. 10 cm occupancy grid + aisle-width dilation + BFS.
# ---------------------------------------------------------------------------

def _mark_rect(grid, x0, z0, w, d, room_w, room_d):
    ax0 = max(0, int(math.floor(x0 * SCALE)))
    az0 = max(0, int(math.floor(z0 * SCALE)))
    ax1 = min(room_w, int(math.ceil((x0 + w) * SCALE)))
    az1 = min(room_d, int(math.ceil((z0 + d) * SCALE)))
    for gx in range(ax0, ax1):
        for gz in range(az0, az1):
            grid[gx][gz] = True


def _dilate(grid, room_w, room_d, r):
    """Chebyshev dilation by r cells (r is small: ~4-5)."""
    out = [row[:] for row in grid]
    for _ in range(r):
        nxt = [row[:] for row in out]
        for gx in range(room_w):
            for gz in range(room_d):
                if out[gx][gz]:
                    continue
                if ((gx > 0 and out[gx - 1][gz]) or (gx < room_w - 1 and out[gx + 1][gz]) or
                        (gz > 0 and out[gx][gz - 1]) or (gz < room_d - 1 and out[gx][gz + 1])):
                    nxt[gx][gz] = True
        out = nxt
    return out


def check_circulation(room, placements, zones_by_id, obstacles=None, min_aisle=None):
    """Verify a person can reach every placed object's interaction zone.

    Returns {"ok": bool, "unreachable": [ids], "checked": n}. Sources are the
    room's doors; without doors, the largest open region of the room.
    """
    if min_aisle is None:
        try:
            pack = rule_packs.get_pack(room.get("type", "office"), bool(room.get("ada")))
            min_aisle = float(pack.get("min_aisle", rule_packs.ANTHRO["aisle"]))
        except Exception:
            min_aisle = 0.9
    room_w = int(room["width"] * SCALE)
    room_d = int(room["depth"] * SCALE)
    if room_w <= 0 or room_d <= 0:
        return {"ok": True, "unreachable": [], "checked": 0}

    blocked = [[False] * room_d for _ in range(room_w)]
    placed = [p for p in placements if p.get("placed") and p.get("rect")]
    for p in placed:
        x0, z0, w, d = p["rect"]
        _mark_rect(blocked, x0, z0, w, d, room_w, room_d)
    for ob in (obstacles or []):
        _mark_rect(blocked, float(ob["x"]), float(ob["z"]),
                   float(ob["width"]), float(ob["depth"]), room_w, room_d)

    r = max(1, int(round(min_aisle / 2 * SCALE)))
    wide_blocked = _dilate(blocked, room_w, room_d, r)
    # a walking person also keeps half an aisle from the walls
    wide_free = [[not wide_blocked[gx][gz] and r <= gx < room_w - r and r <= gz < room_d - r
                  for gz in range(room_d)] for gx in range(room_w)]

    # ---- sources: door rects (dilated into the aisle network) or the open core
    sources = []
    doors = room.get("doors") or []
    for dr in doors:
        dx0 = int(float(dr["x"]) * SCALE); dz0 = int(float(dr["z"]) * SCALE)
        dx1 = dx0 + max(1, int(float(dr["width"]) * SCALE))
        dz1 = dz0 + max(1, int(float(dr.get("depth", dr["width"])) * SCALE))
        for gx in range(max(0, dx0 - r), min(room_w, dx1 + r)):
            for gz in range(max(0, dz0 - r), min(room_d, dz1 + r)):
                if wide_free[gx][gz]:
                    sources.append((gx, gz))
    if not sources:
        # no door given (or door buried): seed from every wide-free cell of the
        # largest open region — the room's own circulation core
        best = None
        seen = [[False] * room_d for _ in range(room_w)]
        for gx in range(room_w):
            for gz in range(room_d):
                if wide_free[gx][gz] and not seen[gx][gz]:
                    comp = []
                    dq = deque([(gx, gz)])
                    seen[gx][gz] = True
                    while dq:
                        cx_, cz_ = dq.popleft()
                        comp.append((cx_, cz_))
                        for nx, nz in ((cx_ + 1, cz_), (cx_ - 1, cz_), (cx_, cz_ + 1), (cx_, cz_ - 1)):
                            if 0 <= nx < room_w and 0 <= nz < room_d and wide_free[nx][nz] and not seen[nx][nz]:
                                seen[nx][nz] = True
                                dq.append((nx, nz))
                    if best is None or len(comp) > len(best):
                        best = comp
        sources = best or []
    if not sources:
        # the room has no aisle-wide open space at all
        ids = [p["id"] for p in placed if zones_by_id.get(p["id"])]
        return {"ok": not ids, "unreachable": ids, "checked": len(ids)}

    # ---- BFS over the aisle-wide network
    reached = [[False] * room_d for _ in range(room_w)]
    dq = deque()
    for gx, gz in sources:
        if not reached[gx][gz]:
            reached[gx][gz] = True
            dq.append((gx, gz))
    while dq:
        gx, gz = dq.popleft()
        for nx, nz in ((gx + 1, gz), (gx - 1, gz), (gx, gz + 1), (gx, gz - 1)):
            if 0 <= nx < room_w and 0 <= nz < room_d and wide_free[nx][nz] and not reached[nx][nz]:
                reached[nx][nz] = True
                dq.append((nx, nz))
    reached_near = _dilate(reached, room_w, room_d, r + 1)

    # ---- every interaction zone must touch the reached network
    unreachable, checked = [], 0
    for p in placed:
        zrects = zones_by_id.get(p["id"])
        if not zrects:
            continue
        checked += 1
        ok = False
        for (zx0, zz0, zw, zd) in zrects:
            gx0 = max(0, int(zx0 * SCALE)); gz0 = max(0, int(zz0 * SCALE))
            gx1 = min(room_w, int(math.ceil((zx0 + zw) * SCALE)))
            gz1 = min(room_d, int(math.ceil((zz0 + zd) * SCALE)))
            for gx in range(gx0, gx1):
                if ok:
                    break
                for gz in range(gz0, gz1):
                    if not blocked[gx][gz] and reached_near[gx][gz]:
                        ok = True
                        break
            if ok:
                break
        if not ok:
            unreachable.append(p["id"])
    return {"ok": not unreachable, "unreachable": unreachable, "checked": checked}


# ---------------------------------------------------------------------------
# A4 — honest diagnostics
# ---------------------------------------------------------------------------

def _diagnose(room, objects, unplaced_ids, obstacles):
    """Human-readable 'not enough space' analysis for the items that didn't fit."""
    if not unplaced_ids:
        return None
    free_area = float(room["width"]) * float(room["depth"])
    for ob in (obstacles or []):
        free_area -= float(ob["width"]) * float(ob["depth"])
    need = 0.0
    for o in objects:
        c = _get_clearance(o)
        w, d = float(o["width"]) + 2 * c, float(o["depth"]) + 2 * c
        need += w * d
        for depth in _profile(o)["zones"].values():
            need += max(w, d) * depth      # zone strip estimate
    shortfall = max(0.0, need - free_area * 0.85)   # ~85 % usable after circulation
    names = [o["id"] for o in objects if o["id"] in set(unplaced_ids)]
    sug = f"Remove {len(names)} item(s)"
    if shortfall > 0.3:
        sug += f" or enlarge the room by ~{shortfall:.1f} m²"
    return {"unplaced": names, "needed_m2": round(need, 1),
            "free_m2": round(free_area, 1), "suggestion": sug + "."}


def layout_room(room, objects, obstacles=None):
    log(f"Room: {room['width']}m × {room['depth']}m, {len(objects)} objects, "
        f"{len(obstacles or [])} obstacles", "info")
    placements, zones_by_id, unplaced = _solve_layout_ortools(room, objects, obstacles)
    circulation = check_circulation(room, placements, zones_by_id, obstacles)
    return {
        "room": room,
        "placements": placements,
        "obstacles": obstacles or [],
        "zones": zones_by_id,
        "solver": "ortools-cpsat",
        "object_count": len(placements),
        "unplaced": unplaced,
        "circulation": circulation,
        "diagnostics": _diagnose(room, objects, unplaced, obstacles),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        error_exit("Usage: spatial_layout.py <room_json> [objects_json]")

    room = json.loads(sys.argv[1])
    objects = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []

    result = layout_room(room, objects)
    success_exit(result)
