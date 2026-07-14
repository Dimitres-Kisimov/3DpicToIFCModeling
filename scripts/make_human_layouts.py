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
    # ---- OFFICE: workstations first, then infrastructure, then everything ----
    ("office_dense", "office", 6, 6,
     items(("desk", 3), ("office_chair", 3), ("monitor", 3), ("cabinet", 1),
           ("printer", 1), ("waste_bin", 1), ("planter", 1))),
    ("office_denser", "office", 6, 6,
     items(("desk", 4), ("office_chair", 4), ("monitor", 4), ("cabinet", 1),
           ("bookshelf", 1), ("printer", 1), ("waste_bin", 2), ("locker", 1),
           ("partition", 1), ("planter", 2))),
    ("office_densest", "office", 6, 6,
     items(("desk", 5), ("office_chair", 5), ("monitor", 5), ("cabinet", 1),
           ("bookshelf", 1), ("printer", 1), ("waste_bin", 2), ("locker", 2),
           ("partition", 2), ("planter", 2), ("fire_extinguisher", 1))),
    ("office_wide_layout", "office", 8, 4.5,
     items(("desk", 4), ("office_chair", 4), ("monitor", 4), ("cabinet", 1),
           ("printer", 1), ("waste_bin", 2), ("planter", 2))),
    # ---- MEETING: table core, then presentation gear ----
    ("meeting_dense", "meeting", 5, 4,
     items(("table", 1), ("office_chair", 6), ("whiteboard", 1))),
    ("meeting_denser", "meeting", 5, 4,
     items(("table", 1), ("office_chair", 8), ("whiteboard", 1),
           ("presentation_screen", 1), ("projector", 1), ("flipchart", 1))),
    ("meeting_densest", "meeting", 6, 5,
     items(("table", 1), ("office_chair", 10), ("whiteboard", 1),
           ("presentation_screen", 1), ("projector", 1), ("flipchart", 1),
           ("water_dispenser", 1), ("cabinet", 1), ("planter", 1))),
    # ---- BREAK (Pausenraum, ASR A4.2): eat, store, recycle ----
    ("break_dense", "break", 5, 4,
     items(("table", 1), ("chair", 4), ("coffee_machine", 1), ("waste_bin", 1))),
    ("break_denser", "break", 5, 4,
     items(("table", 1), ("chair", 4), ("coffee_machine", 1), ("waste_bin", 1),
           ("fridge", 1), ("microwave", 1), ("water_dispenser", 1),
           ("first_aid_cabinet", 1))),
    ("break_densest", "break", 6, 5,
     items(("table", 2), ("chair", 8), ("coffee_machine", 1), ("waste_bin", 2),
           ("fridge", 1), ("microwave", 1), ("water_dispenser", 1), ("sofa", 1),
           ("side_table", 1), ("locker", 2), ("planter", 1),
           ("first_aid_cabinet", 1))),
    # ---- RECEPTION: greet, wait, hang your coat ----
    ("reception_dense", "reception", 5, 3.5,
     items(("desk", 1), ("office_chair", 1), ("monitor", 1), ("armchair", 2),
           ("coat_rack", 1))),
    ("reception_denser", "reception", 5, 3.5,
     items(("desk", 1), ("office_chair", 1), ("monitor", 1), ("armchair", 3),
           ("coat_rack", 1), ("side_table", 1), ("planter", 1), ("waste_bin", 1))),
    ("reception_densest", "reception", 6, 4,
     items(("desk", 1), ("office_chair", 1), ("monitor", 1), ("armchair", 4),
           ("sofa", 1), ("coat_rack", 1), ("side_table", 2), ("planter", 2),
           ("waste_bin", 1), ("water_dispenser", 1))),
    # ---- QUIET (Ruheraum): calm by design — even 'densest' stays sparse ----
    ("quiet_dense", "quiet", 3.5, 3.5,
     items(("armchair", 1), ("side_table", 1), ("planter", 1))),
    ("quiet_denser", "quiet", 3.5, 3.5,
     items(("armchair", 2), ("side_table", 1), ("lamp", 1), ("planter", 1))),
    ("quiet_densest", "quiet", 4.5, 4,
     items(("armchair", 2), ("sofa", 1), ("side_table", 2), ("lamp", 1),
           ("bookshelf", 1), ("planter", 2))),
    # ---- LIVING (residential control group — regression sanity) ----
    ("living_dense", "living", 5, 5,
     items(("sofa", 1), ("coffee_table", 1), ("lamp", 1))),
    ("living_densest", "living", 5, 5,
     items(("sofa", 2), ("coffee_table", 1), ("side_table", 1), ("lamp", 2),
           ("bookshelf", 1), ("planter", 2))),
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
