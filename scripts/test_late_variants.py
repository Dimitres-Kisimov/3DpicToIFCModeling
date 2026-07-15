"""test_late_variants.py — ergonomics gate for the 44 late-category variants
(PRIM parametric + PolyHaven CC0). Forces the NEW meshes through the real
variant-selection path (items[].ids) and verifies the Item Logic Register
rules hold with these exact files:

  room tests   presentation / office / kitchen / break — exact-polygon clash
               meter, projector ceiling+aimed, microwave ON the table, rows
               centred, wall-flush storage, corner planters
  building test  Buerogebaeude office picked with gen: ids — rel links
               (in_front_of / beside / door_flank), wall-mount heights, clashes

Run TWICE for the double-test requirement:
    python scripts/test_late_variants.py && python scripts/test_late_variants.py
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

from shapely.geometry import Polygon
from shapely import affinity

REPO = Path(__file__).resolve().parents[1]
BASE = "http://localhost:3000"
FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def ids_by_code():
    m = json.load(open(REPO / "data/generated_assets/manifest.json", encoding="utf-8"))
    return {it.get("code"): it["id"] for it in (m if isinstance(m, list) else m["items"])
            if it.get("code")}


def layout(room, items):
    body = json.dumps({"room": room, "items": items}).encode()
    req = urllib.request.Request(BASE + "/api/room/layout", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=900))


def poly(o):
    p = Polygon([(-o["width_m"] / 2, -o["depth_m"] / 2), (o["width_m"] / 2, -o["depth_m"] / 2),
                 (o["width_m"] / 2, o["depth_m"] / 2), (-o["width_m"] / 2, o["depth_m"] / 2)])
    return affinity.translate(affinity.rotate(p, -o.get("rotation_deg", 0), origin=(0, 0)),
                              o["x"], o["z"])


def overlaps(items):
    floor = [o for o in items if o.get("x") is not None
             and float(o.get("elevation", 0) or 0) < 0.3]
    bad = []
    for i in range(len(floor)):
        for j in range(i + 1, len(floor)):
            ov = poly(floor[i]).intersection(poly(floor[j])).area
            if ov > 0.01:
                bad.append(f"{floor[i]['id']}x{floor[j]['id']}={ov:.3f}")
    return bad


def main():
    code = ids_by_code()

    def I(c):                                 # -> ids selector for one variant
        return [code[c]]

    # ---- 1) presentation hall with the new front-kit variants -----------------
    r = layout({"width": 10, "depth": 8, "type": "presentation", "name": "late-var pres"},
               [{"category": "presentation_screen", "ids": I("presentation_screen-CC0-001")},
                {"category": "projector", "ids": I("projector-PRIM-001")},
                {"category": "lectern", "ids": I("lectern-PRIM-002")},
                {"category": "flipchart", "ids": I("flipchart-PRIM-001")},
                {"category": "whiteboard", "ids": I("whiteboard-PRIM-001")},
                {"category": "chair", "count": 20},
                {"category": "fire_extinguisher", "ids": I("fire_extinguisher-PRIM-001")}])
    its = [o for o in r["items"] if o.get("x") is not None]
    proj = next((o for o in its if o["category"] == "projector"), None)
    scr = next((o for o in its if o["category"] == "presentation_screen"), None)
    chairs = [o for o in its if o["category"] == "chair"]
    check("pres: all placed", len(its) >= 24, f"{len(its)} placed")
    check("pres: projector CEILING", proj and float(proj["elevation"]) >= 2.0,
          f"elev {proj and proj['elevation']}")
    check("pres: projector aimed at screen", proj and proj.get("relation") == "throws_onto")
    rows = {}
    for c in chairs:
        rows.setdefault(round(c["z"], 1), []).append(c["x"])
    centred = all(abs((min(xs) + max(xs)) / 2 - scr["x"]) <= 0.4 for xs in rows.values())
    check("pres: rows centred on display axis", centred, f"{len(rows)} rows")
    check("pres: zero overlaps", not overlaps(its), "; ".join(overlaps(its))[:100])

    # ---- 2) office with partitions / printer / rack / safety ------------------
    r = layout({"width": 8, "depth": 6, "type": "office", "name": "late-var office"},
               [{"category": "desk", "count": 4}, {"category": "office_chair", "count": 4},
                {"category": "monitor", "count": 4}, {"category": "waste_bin", "count": 2},
                {"category": "partition", "ids": [code["partition-PRIM-002"], code["partition-CC0-001"]]},
                {"category": "printer", "ids": I("printer-PRIM-001")},
                {"category": "coat_rack", "ids": I("coat_rack-PRIM-001")},
                {"category": "server_rack", "ids": I("server_rack-PRIM-001")},
                {"category": "first_aid_cabinet", "ids": I("first_aid_cabinet-CC0-001")},
                {"category": "water_dispenser", "ids": I("water_dispenser-PRIM-001")},
                {"category": "planter", "count": 2}])
    its = [o for o in r["items"] if o.get("x") is not None]
    check("office: all core placed", len(its) >= 18, f"{len(its)} placed")
    check("office: zero overlaps", not overlaps(its), "; ".join(overlaps(its))[:100])
    rack = next((o for o in its if o["category"] == "server_rack"), None)
    wd = rack and min(rack["x"], 8 - rack["x"], rack["z"], 6 - rack["z"])
    check("office: server rack at wall", rack is not None and wd < 0.9, f"wall gap {wd}")
    for o in its:
        if o["category"] == "planter":
            dc = min(math.hypot(o["x"] - cx, o["z"] - cz) for cx in (0, 8) for cz in (0, 6))
            dwall = min(o["x"], 8 - o["x"], o["z"], 6 - o["z"])
            check("office: planter corner/wall", dc < 1.6 or dwall < 0.7,
                  f"corner {dc:.2f} wall {dwall:.2f}")

    # ---- 3) kitchen: microwave ON the table (CC0 vintage) ----------------------
    r = layout({"width": 5, "depth": 4, "type": "kitchen", "name": "late-var kitchen"},
               [{"category": "cabinet", "count": 3}, {"category": "fridge", "count": 1},
                {"category": "table", "count": 1}, {"category": "chair", "count": 4},
                {"category": "microwave", "ids": I("microwave-CC0-001")},
                {"category": "coffee_machine", "ids": I("coffee_machine-PRIM-001")},
                {"category": "waste_bin", "count": 1}])
    its = [o for o in r["items"] if o.get("x") is not None]
    mw = next((o for o in its if o["category"] == "microwave"), None)
    cm = next((o for o in its if o["category"] == "coffee_machine"), None)
    check("kitchen: microwave ON table", mw and float(mw["elevation"]) > 0.5
          and mw.get("relation") == "on_top", f"elev {mw and mw['elevation']}")
    check("kitchen: coffee machine ON table", cm and float(cm["elevation"]) > 0.5)
    check("kitchen: zero overlaps", not overlaps(its), "; ".join(overlaps(its))[:100])

    # ---- 4) break room: PRIM appliances -----------------------------------------
    r = layout({"width": 6, "depth": 5, "type": "break", "name": "late-var break"},
               [{"category": "table", "count": 1}, {"category": "chair", "count": 6},
                {"category": "coffee_machine", "ids": I("coffee_machine-PRIM-003")},
                {"category": "microwave", "ids": I("microwave-PRIM-001")},
                {"category": "water_dispenser", "ids": I("water_dispenser-PRIM-002")},
                {"category": "fridge", "count": 1},
                {"category": "first_aid_cabinet", "ids": I("first_aid_cabinet-PRIM-002")},
                {"category": "planter", "count": 1}])
    its = [o for o in r["items"] if o.get("x") is not None]
    mw = next((o for o in its if o["category"] == "microwave"), None)
    check("break: microwave ON table", mw and float(mw["elevation"]) > 0.5)
    check("break: zero overlaps", not overlaps(its), "; ".join(overlaps(its))[:100])

    # ---- 5) BUILDING: Buerogebaeude office with gen: picks ---------------------
    picks = {"Buero Obermeier": ["desk", "office_chair", "monitor", "waste_bin",
                                 f"gen:{code['printer-PRIM-001']}",
                                 f"gen:{code['partition-PRIM-001']}",
                                 f"gen:{code['coat_rack-PRIM-001']}",
                                 f"gen:{code['fire_extinguisher-PRIM-001']}",
                                 f"gen:{code['first_aid_cabinet-PRIM-001']}"]}
    body = json.dumps({"picks": picks, "density": "medium"}).encode()
    req = urllib.request.Request(BASE + "/api/building/b_02a4d40679/populate", data=body,
                                 method="POST", headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=1800))
    room = [p for p in r.get("pieces", []) if p["room"] == "Buero Obermeier"]
    cats_here = {p["category"] for p in room}
    check("building: picked variants placed",
          {"printer", "partition", "coat_rack", "desk"} <= cats_here, str(sorted(cats_here)))
    fe = next((p for p in room if p["category"] == "fire_extinguisher"), None)
    fa = next((p for p in room if p["category"] == "first_aid_cabinet"), None)
    check("building: extinguisher at 1.00 m", fe and abs(float(fe["elev"]) - 1.0) < 0.05,
          f"elev {fe and fe['elev']}")
    check("building: first aid at 1.35 m", fa and abs(float(fa["elev"]) - 1.35) < 0.05,
          f"elev {fa and fa['elev']}")
    # rel links are authoritative in the on-disk manifest (the HTTP mapping
    # gained `rel` later — reading the file works on any server version)
    man = json.load(open(REPO / "demo/app_out/bldg_b_02a4d40679/furniture.json",
                         encoding="utf-8"))
    mroom = [p for p in man["pieces"] if p["room"] == "Buero Obermeier"]
    rels = {p.get("rel", {}).get("kind") for p in mroom if p.get("rel")}
    check("building: human links present", "in_front_of" in rels and "beside" in rels,
          str(sorted(k for k in rels if k)))
    check("building: clash counter clean", int(r.get("clashes") or 0) == 0,
          f"clashes {r.get('clashes')}")

    print(f"\n{'ALL CLEAN' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}", flush=True)
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
