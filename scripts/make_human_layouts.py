"""make_human_layouts.py — render the human-logic showcase: room types at three
escalating densities (dense / denser / densest) with item combinations a human
would actually choose, through the REAL layout API (CP-SAT + rule packs + ASR).
Each run yields the solver's own floorplan.png + furniture3d.png.

    python scripts/make_human_layouts.py    (server must be running)

Out: docs/human_layouts/<scenario>_plan.png / _3d.png + manifest.json
"""
import json
import shutil
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "human_layouts"
RENDERS = REPO / "demo" / "app_out" / "renders"
BASE = "http://localhost:3000"

def items(*pairs):
    return [{"category": c, "count": n} for c, n in pairs]

SCENARIOS = [
    # ---- OFFICES: four real types a human would recognize -------------------
    ("office_duo", "office", 4.5, 3.5,
     items(("desk", 2), ("office_chair", 2), ("monitor", 2), ("cabinet", 1),
           ("waste_bin", 1), ("coat_rack", 1), ("planter", 1))),
    ("office_team", "office", 6, 6,
     items(("desk", 4), ("office_chair", 4), ("monitor", 4), ("partition", 2),
           ("printer", 1), ("waste_bin", 2), ("bookshelf", 1), ("locker", 2),
           ("planter", 1))),
    ("office_exec", "office", 5, 4.5,
     items(("desk", 1), ("office_chair", 1), ("monitor", 1), ("bookshelf", 2),
           ("armchair", 2), ("side_table", 1), ("coat_rack", 1), ("planter", 1))),
    ("office_open", "office", 10, 8,
     items(("desk", 8), ("office_chair", 8), ("monitor", 8), ("partition", 3),
           ("printer", 1), ("waste_bin", 3), ("locker", 2), ("water_dispenser", 1),
           ("armchair", 2), ("side_table", 1), ("phone_booth", 1), ("planter", 3),
           ("fire_extinguisher", 1), ("first_aid_cabinet", 1))),
    # ---- MEET & PRESENT ------------------------------------------------------
    ("meeting_hub", "meeting", 5, 4,
     items(("table", 1), ("office_chair", 6), ("whiteboard", 1),
           ("presentation_screen", 1), ("projector", 1), ("flipchart", 1),
           ("planter", 1))),
    ("presentation_hall", "presentation", 8, 7,
     items(("presentation_screen", 1), ("lectern", 1), ("projector", 1),
           ("whiteboard", 1), ("chair", 24), ("flipchart", 1),
           ("fire_extinguisher", 1))),
    # ---- EAT & PAUSE ---------------------------------------------------------
    ("break_social", "break", 5, 4,
     items(("table", 1), ("chair", 4), ("coffee_machine", 1), ("microwave", 1),
           ("fridge", 1), ("water_dispenser", 1), ("waste_bin", 1),
           ("first_aid_cabinet", 1), ("planter", 1))),
    ("kitchen_eatin", "kitchen", 5, 4,
     items(("cabinet", 3), ("fridge", 1), ("table", 1), ("chair", 4),
           ("microwave", 1), ("coffee_machine", 1), ("waste_bin", 1),
           ("planter", 1))),
    # ---- WELCOME & FOCUS -----------------------------------------------------
    ("reception_welcome", "reception", 5, 4,
     items(("desk", 1), ("office_chair", 1), ("monitor", 1), ("armchair", 3),
           ("side_table", 1), ("coat_rack", 1), ("planter", 2), ("waste_bin", 1))),
    ("quiet_focus", "quiet", 3.5, 3.5,
     items(("armchair", 2), ("side_table", 1), ("lamp", 1), ("planter", 1),
           ("bookshelf", 1))),
    # ---- RESIDENTIAL CONTROL -------------------------------------------------
    ("living_home", "living", 5, 5,
     items(("sofa", 1), ("coffee_table", 1), ("stool", 2), ("armchair", 1),
           ("side_table", 1), ("table", 1), ("chair", 4), ("lamp", 1),
           ("bookshelf", 1), ("planter", 1))),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, rtype, w, d, its in SCENARIOS:
        body = json.dumps({"room": {"width": w, "depth": d, "type": rtype,
                                    "name": name}, "items": its}).encode()
        req = urllib.request.Request(BASE + "/api/room/layout", data=body,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            r = json.load(urllib.request.urlopen(req, timeout=900))
        except Exception as e:
            print(f"FAIL {name}: {e}")
            results.append({"name": name, "ok": False})
            continue
        placed = len([o for o in r.get("objects", []) if o.get("placed", True)]) \
            or r.get("placed") or len(r.get("objects", []))
        for src, suffix in (("floorplan.png", "_plan.png"), ("furniture3d.png", "_3d.png")):
            p = RENDERS / src
            if p.exists():
                shutil.copy(p, OUT / (name + suffix))
        results.append({"name": name, "type": rtype, "room": f"{w}x{d} m",
                        "items": sum(i["count"] for i in its), "ok": True,
                        "secs": round(time.time() - t0)})
        print(f"OK   {name:22s} {w}x{d} m, {sum(i['count'] for i in its)} items "
              f"({time.time()-t0:.0f}s)")
    (OUT / "manifest.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n{sum(1 for r in results if r['ok'])}/{len(results)} scenarios rendered -> {OUT}")


if __name__ == "__main__":
    main()
