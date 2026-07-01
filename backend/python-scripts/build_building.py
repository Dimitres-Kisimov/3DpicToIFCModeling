"""build_building.py — Phase 2: aggregate rooms into a whole-building POPULATION.

Takes a building spec (storeys -> rooms -> object picks), runs the existing per-room CP-SAT solver
(build_room_scene) for each room, and aggregates everything into ONE building-wide PLACEMENT TABLE plus
an xeokit MetaModel hierarchy. The placement table is what drives smooth *instanced* rendering: each row
is just (asset_id, storey, room, world x/y/z, rotation) referencing the asset library — the mesh itself
lives once in asset_library/, never duplicated. A building with 500 chairs = 1 mesh + 500 table rows.

Outputs (deliverable/building/<name>/):
  building_placement.json / .csv   master table: every furniture instance (asset_id + world transform)
  building_metamodel.json          xeokit MetaModel: Building -> Storey -> Space -> furniture
  building_summary.json            counts: storeys, rooms, instances, unique assets used, categories
  rooms/<storey>/<room>/           per-room solver output (scene.glb + schedule), kept for reference

Building spec (JSON):
{
  "name": "SCS Office Complex",
  "storey_height": 3.5,
  "storeys": [
    {"name": "Ground Floor", "rooms": [
      {"name": "Reception", "type": "office", "width": 6, "depth": 4, "height": 3,
       "objects": [{"category": "sofa", "qty": 2}, {"category": "table", "qty": 1}]}
    ]},
    {"name": "Level 1", "rooms": [ ... ]}
  ]
}

Usage: python build_building.py <building_spec.json> [out_name]
"""
from __future__ import annotations
import sys, os, csv, json, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_room_scene as brs

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "deliverable" / "asset_library"
ROOM_GAP = 1.5   # metres of corridor between rooms in a storey row


def load_library():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], []).append(a)
    for cat in by_cat:                                   # best asset per category first
        by_cat[cat].sort(key=lambda a: -a.get("fscore", 0))
    return by_cat


def build(spec_path: str, out_name: str | None = None) -> dict:
    spec = json.load(open(spec_path, encoding="utf-8"))
    lib = load_library()
    name = out_name or spec.get("name", "building").replace(" ", "_")
    out = REPO / "deliverable" / "building" / name
    (out / "rooms").mkdir(parents=True, exist_ok=True)
    sh = float(spec.get("storey_height", 3.5))

    placement, meta = [], [{"id": "building", "name": spec.get("name", "Building"),
                            "type": "IfcBuilding", "parent": None}]
    used_assets, inst = set(), 0

    for si, storey in enumerate(spec["storeys"]):
        sid = f"storey-{si}"
        elev = si * sh
        meta.append({"id": sid, "name": storey.get("name", f"Storey {si}"),
                     "type": "IfcBuildingStorey", "parent": "building", "elevation_m": elev})
        cursor_x = 0.0                                    # lay rooms left-to-right along X
        for ri, room in enumerate(storey["rooms"]):
            rid = f"{sid}-room-{ri}"
            rw, rd = float(room["width"]), float(room["depth"])
            # assemble a scene_spec from library assets
            objs = []
            for oi, pick in enumerate(room.get("objects", [])):
                cat = pick["category"]
                if cat not in lib:
                    print(f"  [warn] no library asset for '{cat}' — skipped"); continue
                asset = lib[cat][0]
                for q in range(int(pick.get("qty", 1))):
                    objs.append({"id": f"{rid}-{cat}-{oi}-{q}", "name": cat.replace("_", " ").title(),
                                 "category": cat, "ifc_class": asset["ifc_class"],
                                 "dimensions": asset["dimensions_m"], "glb": str(LIB / asset["glb"]),
                                 "source": asset["source_model"], "license": asset["license"],
                                 "_asset_id": asset["asset_id"]})
            room_spec = {"room": {"width": rw, "depth": rd, "height": float(room.get("height", 3.0)),
                                  "name": room.get("name", rid)}, "objects": objs}
            room_out = out / "rooms" / sid / f"room-{ri}"
            brs.build(room_spec, room_out)
            sched = json.load(open(room_out / "schedule.json", encoding="utf-8"))["items"]
            posmap = {o["id"]: o for o in objs}

            meta.append({"id": rid, "name": room.get("name", rid), "type": "IfcSpace",
                         "parent": sid, "room_origin_m": [round(cursor_x, 3), 0.0]})
            for it in sched:
                a = posmap.get(it["id"], {})
                aid = a.get("_asset_id", "")
                used_assets.add(aid)
                placement.append({
                    "instance_id": f"inst-{inst:05d}", "asset_id": aid, "category": it["category"],
                    "storey": storey.get("name", sid), "room": room.get("name", rid),
                    "x": round(cursor_x + it["x"], 3), "y": round(elev, 3), "z": round(it["z"], 3),
                    "rotation_deg": it["rotation_deg"], "scale": 1.0,
                    "ifc_class": it["ifc_class"], "source": it["source"], "license": it["license"],
                })
                meta.append({"id": f"inst-{inst:05d}", "name": it["name"],
                             "type": it["ifc_class"], "parent": rid})
                inst += 1
            cursor_x += rw + ROOM_GAP

    # ---- write the master table + metamodel + summary ----
    (out / "building_placement.json").write_text(
        json.dumps({"building": spec.get("name"), "storey_height_m": sh, "instances": placement}, indent=2),
        encoding="utf-8")
    if placement:
        with open(out / "building_placement.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(placement[0].keys())); w.writeheader(); w.writerows(placement)
    (out / "building_metamodel.json").write_text(json.dumps({"metaObjects": meta}, indent=2), encoding="utf-8")
    summary = {
        "building": spec.get("name"), "storeys": len(spec["storeys"]),
        "rooms": sum(len(s["rooms"]) for s in spec["storeys"]),
        "instances": len(placement), "unique_assets_used": sorted(a for a in used_assets if a),
        "categories": sorted({p["category"] for p in placement}),
        "instancing_ratio": f"{len(placement)} instances from {len([a for a in used_assets if a])} unique meshes",
    }
    (out / "building_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out}/building_placement.(json|csv) + metamodel + summary")
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: build_building.py <building_spec.json> [out_name]"); sys.exit(1)
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
