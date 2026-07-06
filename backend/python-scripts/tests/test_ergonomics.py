"""
Ergonomics engine verification (Part 2, Workstream A) — hand-checked rooms.

Run:  python backend/python-scripts/tests/test_ergonomics.py
Prints one PASS/FAIL line per check and exits non-zero on any failure.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spatial_layout as sl
import rule_packs

FAILURES = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def rects_overlap(a, b):
    ax0, az0, aw, ad = a
    bx0, bz0, bw, bd = b
    return min(ax0 + aw, bx0 + bw) - max(ax0, bx0) > 0.01 and \
           min(az0 + ad, bz0 + bd) - max(az0, bz0) > 0.01


DESK = {"id": "desk-1", "category": "desk", "width": 1.4, "depth": 0.7, "height": 0.74}
CAB = {"id": "cab-1", "category": "cabinet", "width": 1.0, "depth": 0.45, "height": 1.2}
BED = {"id": "bed-1", "category": "bed", "width": 1.6, "depth": 2.05, "height": 0.55}


# 1 ── a 3×3 office with one desk is feasible, with its legroom zone reserved
r = sl.layout_room({"width": 3, "depth": 3, "type": "office"}, [dict(DESK)])
p = r["placements"][0]
check("3x3 office + desk feasible", p["placed"] and not r["unplaced"])
check("desk has a legroom zone", len(r["zones"].get("desk-1", [])) == 1)
zx, zz, zw, zd = r["zones"]["desk-1"][0]
check("legroom zone inside room", zx >= -0.01 and zz >= -0.01 and zx + zw <= 3.01 and zz + zd <= 3.01)
check("legroom zone clear of desk", not rects_overlap(r["zones"]["desk-1"][0], p["rect"]))

# 2 ── seat side never against a wall: the front zone forces >= legroom of open floor
fx, fz = p["front"]
cx, cz = p["position"][0], p["position"][2]
edge = cx + fx * (p["rect"][2] / 2) + cz * 0 if fx else None
front_room = (3 - (cz + p["rect"][3] / 2)) if fz > 0 else (cz - p["rect"][3] / 2) if fz < 0 else \
             (3 - (cx + p["rect"][2] / 2)) if fx > 0 else (cx - p["rect"][2] / 2)
check("desk user side faces open floor (>= 0.5 m)", front_room >= 0.5, f"front_room={front_room:.2f}")

# 3 ── over-pack: 6 desks in 3×3 -> honest per-item 'not enough space' report
r2 = sl.layout_room({"width": 3, "depth": 3, "type": "office"},
                    [dict(DESK, id=f"desk-{i}") for i in range(6)])
check("overpack reports unplaced items", len(r2["unplaced"]) >= 3)
check("overpack diagnostics has suggestion",
      bool(r2["diagnostics"] and r2["diagnostics"].get("suggestion")))
check("overpack still places what fits", any(p["placed"] for p in r2["placements"]))

# 4 ── furniture never overlaps a pillar obstacle
OB = {"x": 2.0, "z": 1.5, "width": 0.5, "depth": 0.5}
r3 = sl.layout_room({"width": 5, "depth": 4, "type": "office"},
                    [dict(DESK), dict(CAB), dict(CAB, id="cab-2")], obstacles=[OB])
ob_rect = [OB["x"], OB["z"], OB["width"], OB["depth"]]
for p in r3["placements"]:
    if p["placed"]:
        check(f"{p['id']} clear of pillar", not rects_overlap(p["rect"], ob_rect))
        check(f"{p['id']} zones clear of pillar",
              all(not rects_overlap(z, ob_rect) for z in r3["zones"].get(p["id"], [])))

# 5 ── door -> every access zone connectivity (circulation)
r4 = sl.layout_room({"width": 5, "depth": 4, "type": "office",
                     "doors": [{"x": 2.2, "z": 3.8, "width": 0.9, "depth": 0.2}]},
                    [dict(DESK), dict(CAB)])
check("circulation from door reaches every zone",
      r4["circulation"]["ok"], json.dumps(r4["circulation"]))

# 6 ── bed access: foot + at least one long side reserved, at real double-bed scale
r5 = sl.layout_room({"width": 4.5, "depth": 4, "type": "office"}, [dict(BED)])
bp = r5["placements"][0]
check("bed placed at real scale", bp["placed"])
check("bed reserves foot + >=1 side", len(r5["zones"].get("bed-1", [])) >= 2)

# 6b ── narrow room (2.9 m wide): bed fits with ONE side to the wall
r5b = sl.layout_room({"width": 2.9, "depth": 4, "type": "office"}, [dict(BED)])
check("bed fits narrow room (one side to wall)", r5b["placements"][0]["placed"])

# 7 ── wall-affine archetypes end with their back at a wall (<= 0.3 m gap)
r6 = sl.layout_room({"width": 5, "depth": 4, "type": "office"}, [dict(DESK), dict(CAB)])
for p in r6["placements"]:
    if not p["placed"]:
        continue
    fx, fz = p["front"]
    x0, z0, w, d = p["rect"]
    if fz > 0:   back_gap = z0
    elif fz < 0: back_gap = 4 - (z0 + d)
    elif fx > 0: back_gap = x0
    else:        back_gap = 5 - (x0 + w)
    check(f"{p['id']} back to wall", back_gap <= 0.35, f"gap={back_gap:.2f}")

# 8 ── archetype sanity after the lounge_seating split
check("sofa is lounge_seating (front approach, back to wall)",
      rule_packs.placement_profile("sofa")["archetype"] == "lounge_seating"
      and "front" in rule_packs.placement_profile("sofa")["zones"])
check("chair keeps pull-out", "back" in rule_packs.placement_profile("office_chair")["zones"])
check("worksurface legroom is front-only",
      list(rule_packs.placement_profile("desk")["zones"].keys()) == ["front"])

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
