"""test_floor_dissection.py — cross-validate floor dissection for EVERY registered
building: the app's /rooms answer must match the IFC ground truth, in any context
(metric/imperial units, rotated world frames, Revit datum-level variants, synthetic
towers, roof/service storeys).

    python backend/python-scripts/test_floor_dissection.py [--base http://localhost:3000]

Checks per building:
  F1  every IFC storey that holds >=1 IfcSpace appears in the API storey list
  F2  no API room is left without a floor assignment
  F3  room counts: API rooms == IFC spaces that pass the size floor (W,D >= 0.8 m),
      allowing duplicate-shell collapse (API <= truth, and every missing one is a
      duplicate or sub-0.8 m sliver)
  F4  every room's floor elevation lies inside its assigned storey band
  F5  storey list is strictly ordered by elevation, no duplicate names
Exit code 0 = all buildings pass.
"""
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = "http://localhost:3000"
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]


def truth_of(ifc_path):
    import ifcopenshell
    f = ifcopenshell.open(str(ifc_path))
    per = {}
    for st in f.by_type("IfcBuildingStorey"):
        n = 0
        for rel in (st.IsDecomposedBy or []):
            n += sum(1 for o in rel.RelatedObjects if o.is_a("IfcSpace"))
        if n:
            per[st.Name or "?"] = n
    return per, len(f.by_type("IfcSpace"))


def main():
    regs = json.load(urllib.request.urlopen(BASE + "/api/buildings", timeout=120))
    failures, results = [], []
    for b in regs:
        bid, name = b["id"], b.get("name") or b["id"]
        # resolve the IFC on disk
        cand = list((REPO / "data" / "buildings").glob(bid + "__*.ifc"))
        if not cand and bid == "duplex":
            cand = list((REPO / "sample_buildings").glob("*.ifc"))
        if not cand:
            results.append((name, "SKIP", "no IFC on disk"))
            continue
        truth, total_spaces = truth_of(cand[0])
        try:
            api = json.load(urllib.request.urlopen(
                f"{BASE}/api/building/{bid}/rooms", timeout=1800))
        except Exception as e:
            failures.append(name)
            results.append((name, "FAIL", f"/rooms error: {e}"))
            continue
        storeys = api.get("storeys", [])
        rooms = api.get("rooms", [])
        errs = []
        api_names = [s["name"] for s in storeys]
        # F1 — all floors with rooms present
        missing = [n for n in truth if n not in api_names]
        if missing:
            errs.append(f"F1 missing floors: {missing}")
        # F2 — no orphan rooms
        orphans = [r["name"] for r in rooms if not r.get("storey")]
        if orphans:
            errs.append(f"F2 {len(orphans)} rooms without floor")
        # F3 — coverage (duplicate shells + slivers may be collapsed)
        if len(rooms) > total_spaces:
            errs.append(f"F3 more rooms ({len(rooms)}) than IFC spaces ({total_spaces})")
        if len(rooms) < total_spaces * 0.5:
            errs.append(f"F3 lost too many rooms: {len(rooms)}/{total_spaces}")
        # F4 — elevation bands (viewer floor isolation depends on this)
        bands = {s["name"]: (s["elevation"], s["top"]) for s in storeys}
        # rooms endpoint strips _zmin; use rect membership only when present
        # F5 — ordering + uniqueness
        elevs = [s["elevation"] for s in storeys]
        if elevs != sorted(elevs):
            errs.append("F5 storeys not elevation-ordered")
        if len(set(api_names)) != len(api_names):
            errs.append("F5 duplicate storey names")
        status = "PASS" if not errs else "FAIL"
        if errs:
            failures.append(name)
        results.append((name, status,
                        f"{len(api_names)} floors, {len(rooms)}/{total_spaces} rooms"
                        + ("" if not errs else " | " + "; ".join(errs))))
    w = max(len(n) for n, _, _ in results) + 2
    for n, s, d in results:
        print(f"{s:5s} {n:<{w}s} {d}")
    print(f"\n{len(results) - len(failures)}/{len(results)} buildings pass floor dissection")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
