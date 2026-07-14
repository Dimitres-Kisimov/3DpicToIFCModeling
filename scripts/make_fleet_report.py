"""make_fleet_report.py — aggregate every populated building's furniture manifest
into one fleet report: pieces by category, HUMAN CONNECTIONS by kind (the rel
field the populate pipeline now exports: chair->desk, monitor->desk, bin->desk,
stools ringing tables, projector->screen, audience rows, door flanks), per
building plus fleet totals.

Run AFTER a fleet populate (scripts run writes demo/app_out/fleet_populate_results.json):
    python scripts/make_fleet_report.py

Out: demo/app_out/fleet_report.json  (served by the app at /out/fleet_report.json,
read by frontend/fleet_report.html in the research hub)."""
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "demo" / "app_out"


def main():
    results_p = OUT_DIR / "fleet_populate_results.json"
    runs = json.load(open(results_p, encoding="utf-8")) if results_p.exists() else []
    name_by_id = {r["id"]: r.get("name") for r in runs}
    buildings = []
    for mdir in sorted(OUT_DIR.glob("bldg_*")):
        bid = mdir.name[5:]
        man_p = mdir / "furniture.json"
        if not man_p.exists():
            continue
        if name_by_id and bid not in name_by_id:
            continue                      # stale dir from a removed building
        man = json.load(open(man_p, encoding="utf-8"))
        pieces = man.get("pieces", [])
        cats, rels, rooms, samples = {}, {}, set(), {}
        for p in pieces:
            cats[p["category"]] = cats.get(p["category"], 0) + 1
            rooms.add(p["room"])
            r = p.get("rel")
            if r:
                rels[r["kind"]] = rels.get(r["kind"], 0) + 1
                samples.setdefault(r["kind"], f"{p['id']} -> {r['to']}  ({p['room']})")
        run = next((x for x in runs if x["id"] == bid), {})
        buildings.append({
            "id": bid, "name": name_by_id.get(bid) or bid,
            "pieces": len(pieces), "rooms": len(rooms),
            "clashes_aabb": run.get("clashes"), "secs": run.get("secs"),
            "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
            "connections": dict(sorted(rels.items(), key=lambda kv: -kv[1])),
            "connection_samples": samples,
        })
    tot_c, tot_r = {}, {}
    for b in buildings:
        for k, v in b["categories"].items():
            tot_c[k] = tot_c.get(k, 0) + v
        for k, v in b["connections"].items():
            tot_r[k] = tot_r.get(k, 0) + v
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "density": "medium",
        "totals": {
            "buildings": len(buildings),
            "rooms": sum(b["rooms"] for b in buildings),
            "pieces": sum(b["pieces"] for b in buildings),
            "connections": sum(tot_r.values()),
            "categories": dict(sorted(tot_c.items(), key=lambda kv: -kv[1])),
            "connections_by_kind": dict(sorted(tot_r.items(), key=lambda kv: -kv[1])),
        },
        "buildings": sorted(buildings, key=lambda b: -b["pieces"]),
    }
    (OUT_DIR / "fleet_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"fleet report: {len(buildings)} buildings, {report['totals']['pieces']} pieces, "
          f"{report['totals']['connections']} connections -> demo/app_out/fleet_report.json")


if __name__ == "__main__":
    main()
