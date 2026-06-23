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
        total = sum(int(p.get("count", 1)) for p in picks)
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
        return jsonify({"ok": True, "feasible": feasible, "solver": res["solver"],
                        "message": msg, "items": sched["items"], "room": sched["room"],
                        "glb": "/out/scene.glb", "ifc": "/out/scene.ifc",
                        "metamodel": "/out/metamodel.json"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "trace": traceback.format_exc()}), 500


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
