"""
app_server.py — SCS room-population app backend (Flask).

Endpoints:
  GET  /api/catalog   -> pickable categories (ABO-backed + dims)
  POST /api/generate  -> {room:{width,depth,type,ada}, items:[{category,count}],
                          obstacles:[{x,z,width,depth,kind}], doors:[{x,z,width,depth}]}
                         -> builds the scene (auto-anchored, constrained layout, IFC)
                         -> {ok, feasible, solver, items[], room, glb, ifc}

Serves the browser UI (demo/app.html) + outputs (/out/...) + the xeokit SDK.
Run: python backend/app_server.py   (then open http://localhost:8000/)
This same UI is what the PySide desktop app embeds for the installable .exe.
"""
from __future__ import annotations

import json
import sys
import shutil
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

HERE = Path(__file__).resolve().parent          # backend/
REPO = HERE.parent                               # repo root
SCRIPTS = HERE / "python-scripts"
sys.path.insert(0, str(SCRIPTS))

import catalog                # noqa: E402
import build_room_scene       # noqa: E402
import build_room_ifc         # noqa: E402
import render_scene           # noqa: E402

OUT = REPO / "demo" / "app_out"    # SCRATCH preview dir — wiped on reset/startup; never a saved deliverable
app = Flask(__name__, static_folder=None)


def _clear_scratch():
    """Remove all generated preview files. Nothing the user generates persists —
    the scene only lives here transiently for the live preview. A real save only
    happens when the user clicks Export (which downloads to their machine)."""
    if OUT.exists():
        for p in OUT.iterdir():
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
            except Exception:
                pass


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, max-age=0"   # dev: always fresh JS/assets
    return resp


@app.get("/api/catalog")
def api_catalog():
    return jsonify(catalog.list_catalog())


@app.get("/api/items/<category>")
def api_items(category):
    return jsonify(catalog.list_items(category))


@app.get("/thumb/<path:fn>")
def thumb(fn):
    return send_from_directory(catalog.ABO_DIR, fn)


@app.post("/api/generate")
def api_generate():
    try:
        body = request.get_json(force=True) or {}
        room = body.get("room", {})
        room.setdefault("height", 3.0)
        room.setdefault("name", "Room")
        for key in ("obstacles", "doors"):
            if body.get(key):
                room[key] = body[key]
        picks = body.get("items", [])
        total = sum(len(p["ids"]) if p.get("ids") else int(p.get("count", 1)) for p in picks)
        if total == 0:
            return jsonify({"ok": False, "error": "select at least one item"}), 400
        if total > 20:
            return jsonify({"ok": False, "error": f"max 20 items ({total} selected)"}), 400

        spec = catalog.build_scene_spec(room, picks)
        OUT.mkdir(parents=True, exist_ok=True)
        res = build_room_scene.build(spec, OUT)
        try:
            build_room_ifc.build(OUT)
        except Exception:
            pass
        try:
            render_scene.main(OUT)
        except Exception:
            pass

        sched = json.loads((OUT / "schedule.json").read_text(encoding="utf-8"))
        feasible = res["solver"] == "ortools-cpsat"
        msg = "Placed all items." if feasible else \
            "Doesn't fit — remove items or enlarge the room."
        # server-rendered images (no WebGL needed) — reliable fallback for the 3D preview
        renders = OUT / "renders"
        render = "/out/renders/furniture3d.png" if (renders / "furniture3d.png").exists() else None
        floorplan = "/out/renders/floorplan.png" if (renders / "floorplan.png").exists() else None
        return jsonify({"ok": True, "feasible": feasible, "solver": res["solver"],
                        "message": msg, "items": sched["items"], "room": sched["room"],
                        "glb": "/out/scene.glb", "ifc": "/out/scene.ifc",
                        "metamodel": "/out/metamodel.json",
                        "render": render, "floorplan": floorplan})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "trace": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Building population: load a REAL architectural IFC, pick furniture per room, populate.
# ---------------------------------------------------------------------------
import populate_building as pop   # noqa: E402

_BUILDINGS = [{"id": "duplex", "name": "Duplex Apartment",
               "ifc": str(REPO / "sample_buildings" / "Duplex_Architecture.ifc")}]


def _building(bid):
    return next((b for b in _BUILDINGS if b["id"] == bid), None)


@app.get("/api/buildings")
def api_buildings():
    return jsonify([{"id": b["id"], "name": b["name"]} for b in _BUILDINGS])


@app.get("/api/building/<bid>/rooms")
def api_building_rooms(bid):
    """Every furnishable room in the building with its type, area, and a space-aware suggestion."""
    b = _building(bid)
    if not b:
        return jsonify({"error": "unknown building"}), 404
    import ifcopenshell, ifcopenshell.geom, numpy as np
    f = ifcopenshell.open(b["ifc"])
    s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
    assets = pop.load_assets()
    seen, rooms = set(), []
    for sp in f.by_type("IfcSpace"):
        name = (sp.LongName or sp.Name or "").strip()
        rt = pop.room_type(name)
        if rt is None or name in seen:
            continue
        try:
            g = ifcopenshell.geom.create_shape(s, sp)
            v = np.array(g.geometry.verts).reshape(-1, 3)
        except Exception:
            continue
        W, D = v[:, 0].max() - v[:, 0].min(), v[:, 1].max() - v[:, 1].min()
        if W < 1.2 or D < 1.2:
            continue
        seen.add(name)
        rooms.append({"name": name, "type": rt, "area": round(W * D, 1),
                      "suggested": pop.smart_furnish(rt, W, D, assets)})
    return jsonify({"rooms": rooms, "categories": sorted(assets.keys())})


@app.post("/api/building/<bid>/populate")
def api_building_populate(bid):
    """Ergonomic populate with the caller's per-room picks -> shell.glb + separate movable pieces."""
    b = _building(bid)
    if not b:
        return jsonify({"error": "unknown building"}), 404
    import subprocess, shutil
    picks = (request.get_json(force=True) or {}).get("picks", {})
    OUT.mkdir(parents=True, exist_ok=True)
    picks_path = OUT / "building_picks.json"
    picks_path.write_text(json.dumps(picks), encoding="utf-8")
    mov = OUT / "bldg"
    shutil.rmtree(mov, ignore_errors=True)
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "populate_building.py"), b["ifc"],
                            str(OUT / "_ignore.glb"), "--picks", str(picks_path), "--movable", str(mov)],
                           capture_output=True, text=True, timeout=600)
        res = json.loads(r.stdout.strip().splitlines()[-1])
        man = json.loads((mov / "furniture.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{exc}"}), 500
    pieces = [{"id": p["id"], "category": p["category"], "glb": f"/out/bldg/{p['glb']}", "pos": p["pos"]}
              for p in man.get("pieces", [])]
    return jsonify({"ok": True, "shell": "/out/bldg/shell.glb", "pieces": pieces,
                    "placed": res.get("furniture_placed"), "rooms": res.get("rooms_populated"),
                    "clashes": res.get("furniture_furniture_clashes"), "schedule": res.get("schedule", [])})


@app.post("/api/building/<bid>/save")
def api_building_save(bid):
    """Merge the current (possibly re-dragged) piece positions + shell into a downloadable GLB."""
    import trimesh
    positions = (request.get_json(force=True) or {}).get("positions", {})   # {piece_id: [x,y,z]}
    mov = OUT / "bldg"
    if not (mov / "shell.glb").exists():
        return jsonify({"ok": False, "error": "populate first"}), 400
    try:
        scene = trimesh.load(str(mov / "shell.glb"), force="scene")
        man = json.loads((mov / "furniture.json").read_text(encoding="utf-8"))
        for p in man.get("pieces", []):
            g = trimesh.load(str(mov / p["glb"]), force="mesh")
            g.apply_translation(positions.get(p["id"], p["pos"]))
            scene.add_geometry(g, node_name=p["id"])
        scene.export(str(OUT / "building_final.glb"))
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{exc}"}), 500
    return jsonify({"ok": True, "glb": "/out/building_final.glb"})


@app.post("/api/reset")
def api_reset():
    """Discard the current preview — restart clean, nothing kept on disk."""
    _clear_scratch()
    return jsonify({"ok": True})


@app.get("/out/<path:p>")
def out_files(p):
    resp = send_from_directory(OUT, p)
    resp.headers["Cache-Control"] = "no-store, max-age=0"   # always refetch on regenerate
    return resp


@app.get("/")
def index():
    return send_from_directory(REPO / "demo", "app.html")


@app.get("/<path:p>")
def static_files(p):
    for base in (REPO / "demo", REPO):
        if (base / p).exists():
            return send_from_directory(base, p)
    return ("not found", 404)


if __name__ == "__main__":
    _clear_scratch()   # start with a clean slate — no leftover preview from a previous run
    print("SCS app on http://localhost:8000/")
    app.run(host="127.0.0.1", port=8000, debug=False)
