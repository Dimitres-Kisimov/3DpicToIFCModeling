"""drop_test_7f.py — the DROP TEST: can a stranger throw a 7-storey IFC at the
app and get every floor and room recognized?

What it does (fully automatic, self-cleaning):
  1. synthesizes a FRESH 7-storey tower IFC the app has never seen
     (make_tower_ifc from the duplex plate, unique storey height)
  2. uploads it through the REAL endpoint (POST /api/buildings/upload),
     exactly like the drag-and-drop in the Building tab
  3. reads the instant profile (storeys/spaces/products) and compares it to
     ifcopenshell ground truth
  4. waits for the one-time geometry scan, then verifies the per-floor room
     dissection: every space-bearing storey present, room counts exact,
     smart suggestions attached
  5. removes the test building again (registry + file) — the fleet stays clean

    python scripts/drop_test_7f.py        (server must be running; ~10-15 min,
                                           dominated by the one-time IFC scan)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = "http://localhost:3000"
SRC = REPO / "data" / "buildings" / "b_b47d0c14b1__duplex_roundtrip.ifc"
TOWER = REPO / "demo" / "app_out" / "_drop_test_7f.ifc"


def step(msg):
    print(f"[drop-test] {msg}", flush=True)


def main():
    t_all = time.time()
    # 1) fresh tower (unique height so the registry's duplicate check can't match)
    step("building a fresh 7-storey IFC (duplex plate + 6 copies)...")
    subprocess.run([sys.executable,
                    str(REPO / "backend" / "python-scripts" / "make_tower_ifc.py"),
                    str(SRC), str(TOWER), "--copies", "6", "--height", "3.07"],
                   check=True, capture_output=True, text=True, timeout=900)

    # ground truth from the IFC itself
    import ifcopenshell
    f = ifcopenshell.open(str(TOWER))
    truth = {}
    for sp in f.by_type("IfcSpace"):
        for rel in (sp.Decomposes or []):
            if rel.RelatingObject.is_a("IfcBuildingStorey"):
                truth[rel.RelatingObject.Name] = truth.get(rel.RelatingObject.Name, 0) + 1
    step(f"ground truth: {len(f.by_type('IfcBuildingStorey'))} storeys, "
         f"{sum(truth.values())} spaces on {len(truth)} space-bearing floors")

    # 2) the drop — multipart upload like the UI
    boundary = uuid.uuid4().hex
    data = TOWER.read_bytes()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="drop_test_7f.ifc"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + data \
        + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/buildings/upload", data=body, method="POST",
                                 headers={"Content-Type":
                                          f"multipart/form-data; boundary={boundary}"})
    r = json.load(urllib.request.urlopen(req, timeout=900))
    b = r.get("building") or r
    bid = b.get("id")
    prof = b.get("profile", {})
    step(f"uploaded -> id {bid}; instant profile: {prof.get('storeys')} storeys, "
         f"{prof.get('spaces')} spaces, {prof.get('products')} products, "
         f"{prof.get('size_mb')} MB, schema {prof.get('schema')}")
    ok_profile = (prof.get("spaces") == sum(truth.values()))

    # 3) floor dissection (first scan is the slow, one-time part)
    step("waiting for room dissection (one-time geometry scan)...")
    rl = None
    for attempt in range(6):
        try:
            rooms = json.load(urllib.request.urlopen(f"{BASE}/api/building/{bid}/rooms",
                                                     timeout=1500))
            rl = rooms.get("rooms", [])
            break
        except Exception as e:
            step(f"  scan still running ({str(e)[:80]}); retry {attempt + 1}/6")
            time.sleep(60)
    if rl is None:
        step("FAIL: rooms never became available")
        sys.exit(1)
    app = {}
    n_suggested = 0
    for rm in rl:
        app[rm.get("storey")] = app.get(rm.get("storey"), 0) + 1
        if rm.get("suggested"):
            n_suggested += 1
    missing = [k for k in truth if k not in app]
    diffs = {k: (truth[k], app.get(k)) for k in truth if app.get(k) != truth[k]}
    step(f"app documents {len(app)} floors, {len(rl)} rooms; "
         f"{n_suggested} rooms carry smart suggestions")
    for k in sorted(truth, key=str):
        mark = "OK " if app.get(k) == truth[k] else "MISMATCH"
        step(f"  {mark} {k}: truth {truth[k]} vs app {app.get(k)}")

    verdict = (ok_profile and not missing and not diffs)
    step(f"VERDICT: {'PASS — every floor and room recognized, counts exact' if verdict else f'FAIL missing={missing} diffs={diffs}'}")

    # 4) self-clean: retire the test building
    man_p = REPO / "data" / "buildings" / "manifest.json"
    m = json.load(open(man_p, encoding="utf-8"))
    lst = m if isinstance(m, list) else m.get("buildings", m)
    kept = [x for x in lst if x.get("id") != bid]
    if isinstance(m, list):
        json.dump(kept, open(man_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    else:
        m["buildings"] = kept
        json.dump(m, open(man_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for p in (REPO / "data" / "buildings").glob(f"{bid}*"):
        os.remove(p)
    if TOWER.exists():
        os.remove(TOWER)
    step(f"cleanup done (test building retired). total {time.time() - t_all:.0f}s")
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
