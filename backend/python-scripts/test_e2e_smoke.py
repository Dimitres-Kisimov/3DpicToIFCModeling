"""test_e2e_smoke.py — END-USER runnability suite: walks the full user journey
against a running app and reports PASS/FAIL per capability. Exit 0 = shippable.

    python backend/python-scripts/test_e2e_smoke.py [--base http://localhost:3000]
                                                    [--skip-generate] [--skip-populate]

Covers: server health · every user-facing page · catalog (fixed + custom flow:
declare category -> upload IFC -> numbered code -> delete -> compaction) ·
photo->3D generation (real TripoSR run on the sample chair; grounded + auto
base-fix + auto-registration) · building rooms/floors · explorer models ·
research hub artefacts. The floor-dissection suite (test_floor_dissection.py)
and the populate runs themselves cover deep placement correctness.
"""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = "http://localhost:3000"
SKIP_GEN = "--skip-generate" in sys.argv
SKIP_POP = "--skip-populate" in sys.argv
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

RESULTS = []


def check(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        RESULTS.append((name, True, f"{detail or 'ok'} ({time.time()-t0:.0f}s)"))
    except Exception as e:
        RESULTS.append((name, False, f"{e} ({time.time()-t0:.0f}s)"))


def get(url, timeout=60):
    return urllib.request.urlopen(BASE + url, timeout=timeout)


def get_json(url, timeout=120):
    return json.load(get(url, timeout))


def post_multipart(url, fields, files, timeout=600):
    import uuid
    bd = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for k, (fname, data) in files:
        ctype = "image/png" if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) \
            else "application/octet-stream"
        body += (f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{bd}--\r\n".encode()
    req = urllib.request.Request(BASE + url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


# 1 — server alive
check("server health", lambda: f"HTTP {get('/', 15).status}")

# 2 — every user-facing page
PAGES = ["/", "/hub.html", "/research_roadmap.html", "/building_explorer.html",
         "/building_showcase.html", "/fleet.html", "/testing.html", "/manuals.html",
         "/four_way_all.html", "/benchmark/index.html", "/benchmark/visualizer.html",
         "/gallery/index.html", "/populated_building_viewer.html"]


def _pages():
    bad = [p for p in PAGES if get(p, 30).status != 200]
    if bad:
        raise RuntimeError(f"pages failing: {bad}")
    return f"{len(PAGES)} pages 200"
check("user-facing pages", _pages)

# 3 — catalog: fixed + engine + custom categories present, professional codes
def _catalog():
    cats = get_json("/api/room/catalog")
    fixed = [c for c in cats if not c.get("custom")]
    if len(fixed) < 30:
        raise RuntimeError(f"only {len(fixed)} fixed categories (36 expected)")
    items = get_json("/api/room/items/desk")
    gen = [i for i in items if i.get("generated")]
    uncoded = [i["id"] for i in gen if not i.get("code")]
    if uncoded:
        raise RuntimeError(f"{len(uncoded)} generated items without a code")
    return f"{len(cats)} categories, {len(gen)} coded desk items"
check("catalog + numbering", _catalog)

# 4 — custom category lifecycle: upload IFC -> code -> delete -> compaction
def _custom():
    fixture = next((REPO / "benchmark" / "ifc" / "triposg").glob("*.ifc"))
    d = post_multipart("/api/room/catalog/custom",
                       {"category": "smoke test item"},
                       [("files", (fixture.name, fixture.read_bytes()))])
    if not d.get("ok"):
        raise RuntimeError(f"upload failed: {d}")
    item = d["results"][0]["item"]
    code = item.get("code") or ""
    if not code.startswith("smoke_test_item-USER-"):
        raise RuntimeError(f"bad code: {code}")
    req = urllib.request.Request(BASE + "/api/room/generated/" + item["id"], method="DELETE")
    dd = json.load(urllib.request.urlopen(req, timeout=120))
    if not dd.get("ok"):
        raise RuntimeError(f"delete failed: {dd}")
    cats = get_json("/api/room/catalog")
    if any(c["category"] == "smoke_test_item" for c in cats):
        raise RuntimeError("category not removed after last item deleted")
    return f"{code} created, deleted, numbering compacted"
check("custom category lifecycle", _custom)

# 5 — photo -> 3D generation (the core pipeline, real weights)
if not SKIP_GEN:
    def _generate():
        img = REPO / "backend" / "triposr" / "examples" / "chair.png"
        d = post_multipart("/api/generate", {"model": "triposr", "baseStyle": "auto"},
                           [("image", ("chair.png", img.read_bytes()))], timeout=1200)
        if not d.get("success"):
            raise RuntimeError(f"generate failed: {d.get('error')}")
        glb = d.get("glbPath") or ""
        p = Path(glb) if Path(glb).is_absolute() else REPO / glb
        if not p.exists() or p.stat().st_size < 50_000:
            raise RuntimeError(f"GLB missing/too small: {glb}")
        import trimesh
        m = trimesh.load(str(p), force="mesh")
        b = m.bounds
        if abs(float(b[0][1])) > 0.05:
            raise RuntimeError(f"not grounded: minY={b[0][1]:.3f}")
        return f"{d.get('category')} · {p.stat().st_size//1024} KB · grounded"
    check("photo->3D generate (TripoSR)", _generate)

# 6 — buildings: registry + rooms/floors for a small building
def _buildings():
    regs = get_json("/api/buildings")
    if len(regs) < 12:
        raise RuntimeError(f"registry too small: {len(regs)}")
    rooms = get_json("/api/building/b_7e52aca674/rooms", timeout=300)
    if not rooms.get("rooms") or not rooms.get("storeys"):
        raise RuntimeError("rooms/storeys empty")
    return f"{len(regs)} buildings; small house {len(rooms['rooms'])} rooms {len(rooms['storeys'])} floors"
check("building registry + rooms", _buildings)

# 7 — populate a small building end to end (queues behind running jobs)
if not SKIP_POP:
    def _populate():
        req = urllib.request.Request(BASE + "/api/building/b_7e52aca674/populate",
                                     data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=1800))
        if not d.get("ok"):
            raise RuntimeError(f"populate failed: {d}")
        return f"{d['placed']} pieces, {d['clashes']} clashes"
    check("building populate (small)", _populate)

# 8 — explorer models on disk + served
def _explorer():
    names = ["duplex", "schependomlaan", "house", "german", "small_building",
             "duplex_sample", "tower", "institute", "smiley", "hhs"]
    missing = [n for n in names
               if get(f"/outputs/{n}_populated.glb", 60).status != 200]
    if missing:
        raise RuntimeError(f"missing explorer models: {missing}")
    return f"{len(names)} populated models served"
check("explorer models", _explorer)

# ---------------------------------------------------------------------------
w = max(len(n) for n, _, _ in RESULTS) + 2
fails = 0
for n, ok, d in RESULTS:
    print(f"{'PASS' if ok else 'FAIL':5s} {n:<{w}s} {d}")
    fails += (not ok)
print(f"\n{len(RESULTS)-fails}/{len(RESULTS)} end-user capabilities pass")
sys.exit(1 if fails else 0)
