"""
room_api.py — single CLI dispatcher for every room / building / catalog operation.

This replaces backend/app_server.py's in-process Flask glue so the Node server
(:3000) can drive the SAME Python engine through one uniform contract:

    python room_api.py <command> [@args.json | '<inline-json>']

The result is printed as JSON on the LAST stdout line (the contract the Node
pythonBridge already parses). Handled errors also print JSON ({"ok": false,
"error": ...}) and exit 0 — the Node route decides the HTTP status from "ok".

Commands
  catalog                                   -> pickable categories (ABO + generated counts)
  items            {category}               -> per-category mesh list for the picker
  layout           {room, items, out_dir}   -> spec -> scene.glb -> scene.ifc -> renders
  building_rooms   {ifc}                    -> furnishable rooms + smart suggestions
  building_save    {out_dir, positions}     -> merge dragged pieces + shell -> building_final.glb
  register_upload  {path, orig_name, category?} -> categorize + register a user .glb/.ifc
  demo_run         {spec_path, out_dir}     -> canned demo: scene + IFC + renders

populate_building.py keeps its own CLI (it is already subprocess-clean) — Node
spawns it directly, same as Flask did.

Designed so these handlers can later run inside a persistent warm worker
(reading one command per stdin line) with no change to the request shapes.
Windows-first: pathlib everywhere, explicit UTF-8, no POSIX assumptions.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent           # backend/python-scripts
REPO = HERE.parent.parent                        # repo root
sys.path.insert(0, str(HERE))

import catalog                # noqa: E402  (light: pure data + manifest reads)

GEN_DIR = REPO / "data" / "generated_assets"     # persisted user-generated assets
GEN_MANIFEST = GEN_DIR / "manifest.json"
_ALLOWED_EXT = {".glb", ".ifc"}

# catalog categories we may map a generated asset to (kept in sync with catalog.CATALOG_META)
_VALID_CATS = set(getattr(catalog, "CATALOG_META", {}).keys()) or {
    "desk", "office_chair", "cabinet", "filing_cabinet", "bookshelf", "sofa", "table",
    "coffee_table", "side_table", "stool", "lamp", "monitor", "laptop", "planter",
    "mirror", "clock", "picture_frame"}

# filename keyword -> category (first match wins; order matters: 'coffee' before 'table')
_NAME_HINTS = [
    ("office_chair", "office_chair"), ("desk", "desk"), ("bookshelf", "bookshelf"),
    ("bookcase", "bookshelf"), ("filing", "filing_cabinet"), ("cabinet", "cabinet"),
    ("coffee", "coffee_table"), ("side_table", "side_table"), ("sidetable", "side_table"),
    ("sofa", "sofa"), ("couch", "sofa"), ("stool", "stool"), ("lamp", "lamp"),
    ("planter", "planter"), ("mirror", "mirror"), ("clock", "clock"),
    ("picture", "picture_frame"), ("frame", "picture_frame"), ("monitor", "monitor"),
    ("laptop", "laptop"), ("chair", "office_chair"), ("table", "table"), ("bed", "table"),
]


# ---------------------------------------------------------------------------
# helpers (ported 1:1 from app_server.py so behavior is unchanged)
# ---------------------------------------------------------------------------

def _safe_cat(cat):
    """Only accept a category the catalog actually knows; else None."""
    cat = (cat or "").strip().lower()
    return cat if cat in _VALID_CATS else None


def _cat_from_name(name):
    low = (name or "").lower()
    for kw, cat in _NAME_HINTS:
        if kw in low:
            return cat
    return None


def _cat_from_ifc(path):
    """Inspect an IFC's furniture element class/name to pick a catalog category.

    Robust across IFC schemas: some classes (e.g. IfcChair) don't exist in IFC4 and
    make by_type raise, so every lookup is individually guarded."""
    try:
        import ifcopenshell
        f = ifcopenshell.open(str(path))

        def _bt(cls):
            try:
                return f.by_type(cls)
            except Exception:
                return []

        if _bt("IfcChair"):
            return "office_chair"
        if _bt("IfcTable"):
            return "table"
        if _bt("IfcSofa"):
            return "sofa"

        furn = _bt("IfcFurniture") + _bt("IfcFurnishingElement")
        for el in furn:
            hint_src = " ".join(str(getattr(el, a, "") or "")
                                for a in ("PredefinedType", "ObjectType", "Name", "Description"))
            hinted = _cat_from_name(hint_src)
            if hinted:
                return hinted
        if furn:
            return "cabinet"      # generic furniture with no usable name hint
    except Exception:
        pass
    return None


def _read_gen_manifest():
    """Return the generated-assets manifest dict; a fresh one if missing/unreadable."""
    try:
        return json.loads(GEN_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}


def _mesh_dims(path):
    """Real extents [x,y,z] of a mesh via trimesh; None on any failure."""
    try:
        import trimesh
        m = trimesh.load(str(path), force="scene")
        ext = m.bounding_box.extents if hasattr(m, "bounding_box") else None
        if ext is not None:
            return [round(float(v), 3) for v in ext]
    except Exception:
        pass
    return None


def _secure_stem(name):
    """Filesystem-safe file stem (werkzeug-free so deployment needs no Flask)."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "").strip()).strip("._")
    return stem or "asset"


def _build_outputs(out_dir: Path):
    """Run scene -> IFC -> renders for a spec already materialised into out_dir,
    then assemble the same response shape Flask's /api/generate returned."""
    import build_room_ifc
    import render_scene
    try:
        build_room_ifc.build(out_dir)
    except Exception:
        pass                                    # IFC failure is non-fatal (as before)
    try:
        render_scene.main(out_dir)
    except Exception:
        pass                                    # render failure is non-fatal (as before)

    sched = json.loads((out_dir / "schedule.json").read_text(encoding="utf-8"))
    renders = out_dir / "renders"
    render = "/out/renders/furniture3d.png" if (renders / "furniture3d.png").exists() else None
    floorplan = "/out/renders/floorplan.png" if (renders / "floorplan.png").exists() else None
    return sched, render, floorplan


# ---------------------------------------------------------------------------
# command handlers
# ---------------------------------------------------------------------------

def cmd_catalog(_args):
    return {"ok": True, "categories": catalog.list_catalog()}


def cmd_items(args):
    category = args.get("category") or ""
    return {"ok": True, "items": catalog.list_items(category)}


def cmd_layout(args):
    """Full single-room layout — ported 1:1 from Flask api_generate()."""
    import build_room_scene
    room = args.get("room", {}) or {}
    room.setdefault("height", 3.0)
    room.setdefault("name", "Room")
    for key in ("obstacles", "doors"):
        if args.get(key):
            room[key] = args[key]
    picks = args.get("items", [])
    total = sum(len(p["ids"]) if p.get("ids") else int(p.get("count", 1)) for p in picks)
    if total == 0:
        return {"ok": False, "error": "select at least one item", "status": 400}
    if total > 20:
        return {"ok": False, "error": f"max 20 items ({total} selected)", "status": 400}

    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = catalog.build_scene_spec(room, picks)
    res = build_room_scene.build(spec, out_dir)

    sched, render, floorplan = _build_outputs(out_dir)
    feasible = res["solver"] == "ortools-cpsat"
    unplaced = sched.get("unplaced") or []
    circ = sched.get("circulation") or {}
    diag = sched.get("diagnostics") or {}
    if feasible and circ.get("ok", True):
        msg = "Placed all items — with room for people to move."
    elif not feasible:
        names = ", ".join(u["name"] for u in unplaced) or "some items"
        msg = (f"Not enough space for: {names}. "
               + (diag.get("suggestion") or "Remove items or enlarge the room."))
    else:
        blocked = ", ".join(circ.get("unreachable") or [])
        msg = f"Placed, but hard to reach: {blocked} — consider fewer items or a wider room."
    return {"ok": True, "feasible": feasible, "solver": res["solver"],
            "message": msg, "items": sched["items"], "room": sched["room"],
            "unplaced": unplaced, "circulation": circ or None,
            "zones": sched.get("zones") or {},
            "glb": "/out/scene.glb", "ifc": "/out/scene.ifc",
            "metamodel": "/out/metamodel.json",
            "render": render, "floorplan": floorplan}


def cmd_building_rooms(args):
    """Furnishable rooms + smart suggestions — ported 1:1 from api_building_rooms()."""
    import ifcopenshell
    import ifcopenshell.geom
    import numpy as np
    import populate_building as pop

    ifc_path = args.get("ifc")
    if not ifc_path or not Path(ifc_path).exists():
        return {"ok": False, "error": "unknown building", "status": 404}
    f = ifcopenshell.open(str(ifc_path))
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
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
        rooms.append({"name": name, "type": rt, "area": round(float(W * D), 1),
                      "suggested": pop.smart_furnish(rt, W, D, assets)})
    return {"ok": True, "rooms": rooms, "categories": sorted(assets.keys())}


def cmd_building_save(args):
    """Merge the current (possibly re-dragged) piece positions + shell into one GLB."""
    import trimesh
    out_dir = Path(args["out_dir"])
    positions = args.get("positions", {}) or {}       # {piece_id: [x,y,z]}
    mov = out_dir / "bldg"
    if not (mov / "shell.glb").exists():
        return {"ok": False, "error": "populate first", "status": 400}
    scene = trimesh.load(str(mov / "shell.glb"), force="scene")
    man = json.loads((mov / "furniture.json").read_text(encoding="utf-8"))
    for p in man.get("pieces", []):
        g = trimesh.load(str(mov / p["glb"]), force="mesh")
        g.apply_translation(positions.get(p["id"], p["pos"]))
        scene.add_geometry(g, node_name=p["id"])
    scene.export(str(out_dir / "building_final.glb"))
    return {"ok": True, "glb": "/out/building_final.glb"}


def cmd_register_upload(args):
    """Categorize + register an uploaded .glb/.ifc that Node (multer) already saved
    to a temp path. Moves it into data/generated_assets/ under a manifest id."""
    src = Path(args["path"])
    orig = args.get("orig_name") or src.name
    ext = Path(orig).suffix.lower()
    if ext not in _ALLOWED_EXT:
        return {"ok": False, "error": "only .glb or .ifc accepted", "status": 400}
    if not src.exists() or src.stat().st_size == 0:
        return {"ok": False, "error": "empty file", "status": 400}

    GEN_DIR.mkdir(parents=True, exist_ok=True)
    uid = "gen_" + uuid.uuid4().hex[:12]
    fn = f"{uid}__{_secure_stem(Path(orig).stem)}{ext}"
    dest = GEN_DIR / fn
    dest.write_bytes(src.read_bytes())
    if not args.get("keep_source"):                    # B3 auto-register keeps the
        try:                                           # original in /outputs — the
            src.unlink()                               # viewer still needs it there
        except Exception:
            pass

    # ---- category resolution (same priority order as before) -----------------
    client_cat = _safe_cat(args.get("category"))
    if ext == ".ifc":
        cat = client_cat or _cat_from_ifc(dest) or _cat_from_name(orig) or "table"
    else:  # .glb
        cat = client_cat or _cat_from_name(orig) or "table"

    dims = _mesh_dims(dest)                            # may be None (.ifc / unreadable)

    item = {"id": uid, "category": cat, "glb": fn, "dims_m": dims,
            "generated": True, "source_file": orig}
    man = _read_gen_manifest()
    man.setdefault("items", []).append(item)
    GEN_MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")

    return {"ok": True, "item": {"id": uid, "category": cat,
                                 "dims_m": dims, "generated": True}}


def cmd_demo_run(args):
    """One-click demo: run a canned scene spec through the full pipeline."""
    import build_room_scene
    spec_path = Path(args.get("spec_path") or (REPO / "demo" / "scene_spec.json"))
    if not spec_path.exists():
        return {"ok": False, "error": f"spec not found: {spec_path}", "status": 404}
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    res = build_room_scene.build(spec, out_dir)

    sched, render, floorplan = _build_outputs(out_dir)
    feasible = res["solver"] == "ortools-cpsat"
    return {"ok": True, "feasible": feasible, "solver": res["solver"],
            "message": "Demo scene built.", "items": sched["items"], "room": sched["room"],
            "glb": "/out/scene.glb", "ifc": "/out/scene.ifc",
            "metamodel": "/out/metamodel.json",
            "render": render, "floorplan": floorplan}


_COMMANDS = {
    "catalog": cmd_catalog,
    "items": cmd_items,
    "layout": cmd_layout,
    "building_rooms": cmd_building_rooms,
    "building_save": cmd_building_save,
    "register_upload": cmd_register_upload,
    "demo_run": cmd_demo_run,
}


def _load_args(raw):
    """Args come inline ('{...}') or as a file reference ('@C:\\path\\args.json') —
    the @file form is what Node uses to dodge Windows command-line quoting."""
    if not raw:
        return {}
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def main(argv):
    if len(argv) < 2 or argv[1] not in _COMMANDS:
        print(json.dumps({"ok": False,
                          "error": f"usage: room_api.py <{'|'.join(_COMMANDS)}> [@args.json|json]"}))
        return 1
    try:
        args = _load_args(argv[2] if len(argv) > 2 else "")
        result = _COMMANDS[argv[1]](args)
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "trace": traceback.format_exc()}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
