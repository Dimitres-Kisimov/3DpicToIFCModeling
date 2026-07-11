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


def _canonicalize_seat_upright(m):
    """Upright a SEATING mesh in the Y-up GLB frame. Photo->3D chairs come out in
    arbitrary orientations (a tilted chair then haunts every room/building it is
    placed in); category ergonomics (desk pairing, facing, pull-out zones) assume
    upright. OBB-align, tallest axis -> +Y (chairs are taller than wide), flip so
    the big shell (backrest+seat) is on top and the sparse legs/base below, then
    ground at y=0 and centre in XZ. Yaw is left alone — the chair-forward
    heuristic finds the backrest later. Applied ONLY to seating at registration;
    deliberately NOT part of the generate pipeline (see office-chair base graft)."""
    import numpy as np
    import trimesh
    T, ext = trimesh.bounds.oriented_bounds(m)
    m.apply_transform(T)
    up = int(np.argmax(ext))
    if up == 0:
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    elif up == 2:
        m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    # flip test: a seat's THINNEST interior band (legs / gas column) sits in the
    # lower half when upright; the bulky seat+backrest live up top. Surface-area
    # comparisons fail here (a chunky seat out-areas the backrest) — width wins.
    v = m.vertices
    y0, y1 = float(v[:, 1].min()), float(v[:, 1].max())
    rel = (v[:, 1] - y0) / max(y1 - y0, 1e-6)
    widths = []
    for i in range(1, 9):                              # interior bands only
        sel = v[(rel >= i / 10) & (rel < (i + 1) / 10)]
        widths.append(float(np.ptp(sel[:, 0]) * np.ptp(sel[:, 2])) if len(sel) >= 10 else np.inf)
    if np.isfinite(min(widths)) and (int(np.argmin(widths)) + 1.5) / 10 > 0.5:
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    return m


_SEATING_CATS = {"office_chair", "chair", "stool"}


def _secure_stem(name):
    """Filesystem-safe file stem (werkzeug-free so deployment needs no Flask)."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "").strip()).strip("._")
    return stem or "asset"


def _render_thumb(mesh_path, out_png, size=256):
    """C2 — offscreen isometric thumbnail of a mesh via matplotlib (rendered ONCE
    at registration, cached forever; no GL context needed on a headless server)."""
    try:
        import numpy as np
        import trimesh
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import PolyCollection

        m = trimesh.load(str(mesh_path), force="mesh")
        if not isinstance(m, trimesh.Trimesh) or m.faces.shape[0] == 0:
            return False
        faces = m.faces
        face_cols = None
        try:
            fc = m.visual.to_color().face_colors            # keep the mesh's own colours
            face_cols = np.asarray(fc[:, :3], dtype=float) / 255.0
        except Exception:
            pass
        if len(faces) > 60000:                              # thumbnails tolerate sampling
            idx = np.random.RandomState(0).choice(len(faces), 60000, replace=False)
            faces = faces[idx]
            face_cols = face_cols[idx] if face_cols is not None else None

        v = m.vertices - m.bounding_box.centroid
        ry, rx = np.radians(-35), np.radians(20)            # isometric-ish view (Y-up)
        Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
        Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
        p = v @ Ry.T @ Rx.T
        tri = p[faces]
        order = np.argsort(tri[:, :, 2].mean(axis=1))       # painter's algorithm
        tri = tri[order]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)
        light = np.array([0.4, 0.8, 0.45]); light /= np.linalg.norm(light)
        lum = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
        base = face_cols[order] if face_cols is not None else np.array([[0.72, 0.62, 0.48]])
        cols = np.clip(lum[:, None] * base, 0, 1)

        fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
        ax.add_collection(PolyCollection(tri[:, :, :2], facecolors=cols, edgecolors="none"))
        pad = 0.05 * max(float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1])))   # numpy 2.x: no ndarray.ptp
        ax.set_xlim(p[:, 0].min() - pad, p[:, 0].max() + pad)
        ax.set_ylim(p[:, 1].min() - pad, p[:, 1].max() + pad)
        ax.set_aspect("equal")
        fig.savefig(str(out_png), transparent=True)
        plt.close(fig)
        return True
    except Exception:
        return False


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
    if total > 120:
        return {"ok": False, "error":
                f"{total} items exceeds the solver's practical capacity for one room (120) — "
                "the constraint model grows quadratically; split the load", "status": 400}

    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = catalog.build_scene_spec(room, picks)

    # count-free feasibility: item quantity is unlimited, floor area is not.
    # Wall-mounted decor and on-desk screens cost no floor; for the rest, even
    # a PERFECT tiling cannot exceed the floor itself — past that bound the
    # answer is a message, not a solve.
    import rule_packs
    floor_area = float(room.get("width", 8)) * float(room.get("depth", 6))
    footprint = 0.0
    for o in spec.get("objects", []):
        dm = o.get("dimensions", {})
        if rule_packs.archetype_of(o.get("category", ""), dm) in ("on_surface", "wall_mounted"):
            continue
        footprint += float(dm.get("width", 0.5)) * float(dm.get("depth", 0.5))
    if footprint > 0.85 * floor_area:
        return {"ok": False, "error":
                f"not enough space: ~{footprint:.1f} m2 of furniture footprint cannot fit a "
                f"{floor_area:.1f} m2 room even without people-space — remove items or "
                "enlarge the room", "status": 400}
    # persist the spec so manual 2D edits can rebuild the GLB without re-solving
    (out_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
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


def _storey_of_space(sp):
    """A space's storey via Decomposes OR ContainedInStructure (exporters vary)."""
    for rel in (sp.Decomposes or []):
        if rel.RelatingObject.is_a("IfcBuildingStorey"):
            return rel.RelatingObject.Name
    for rel in (getattr(sp, "ContainedInStructure", None) or []):
        st = getattr(rel, "RelatingStructure", None)
        if st is not None and st.is_a("IfcBuildingStorey"):
            return st.Name
    return None


def cmd_building_rooms(args):
    """Furnishable rooms + smart suggestions + FLOOR navigation data for ANY IFC:
    storeys (name/elevation/top — unit-normalised, synthesised from geometry when
    the file has none), per room its storey, world footprint rect and labeled
    obstacles/doors. Unknown-named rooms ('Zimmer 1.02') are still furnishable —
    keywords only drive the default suggestions. Mirrored units stay distinct."""
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

    # geometry (create_shape) is ALWAYS metres; raw attributes like Elevation are
    # in project units — normalise them (a Revit mm file would otherwise put
    # storeys at 3100 while rooms sit at 3.1)
    try:
        from ifcopenshell.util.unit import calculate_unit_scale
        unit_scale = float(calculate_unit_scale(f))
    except Exception:
        unit_scale = 1.0

    def _bt(t):
        try:
            return f.by_type(t)
        except Exception:
            return []

    elev_of = {}
    for i, st in enumerate(_bt("IfcBuildingStorey")):
        nm = (st.Name or f"Level {i + 1}").strip()
        elev_of[nm] = float(st.Elevation or 0.0) * unit_scale
    if elev_of and max(abs(v) for v in elev_of.values()) > 500:
        elev_of = {}                                  # broken data — fall back to geometry

    obstacle_rects, door_rects = pop.cached_footprints(f, s, ifc_path)

    seen, rooms = set(), []
    for sp in _bt("IfcSpace"):
        name = (sp.LongName or sp.Name or "").strip()
        cls = pop.classify_room(name)                 # 'skip' | type | None (unknown)
        storey = _storey_of_space(sp)
        ext = pop.space_extent(sp, s, unit_scale)     # solid geometry OR bbox fallback
        if ext is None:
            continue
        x0, x1, y0, y1, zmin = ext
        W, D = x1 - x0, y1 - y0
        if W < 0.8 or D < 0.8:
            continue
        key = (name, storey, round(x0, 1), round(y0, 1))
        if key in seen:
            continue                                  # duplicate shell of the same room
        seen.add(key)
        area = round(float(W * D), 1)
        rec = {"name": name or "Room", "area": area, "storey": storey,
               "rect": [round(x0, 3), round(y0, 3), round(W, 3), round(D, 3)],
               "_zmin": round(float(zmin), 3)}
        # furnishable = big enough and not a service space; unknown names count
        furnishable = cls != "skip" and W >= 1.2 and D >= 1.2 and area >= 4.0
        if furnishable:
            rt = cls if cls not in (None, "skip") else None
            rooms.append({**rec, "type": rt or "room", "furnishable": True,
                          "obstacles": pop.extract_room_obstacles(obstacle_rects, door_rects,
                                                                  x0, x1, y0, y1),
                          "suggested": pop.smart_furnish(rt, W, D, assets) if rt else []})
        else:
            rooms.append({**rec, "type": "space", "furnishable": False,
                          "obstacles": [], "suggested": []})

    if not rooms:
        return {"ok": False, "status": 400,
                "error": "no usable rooms found — the IFC has no IfcSpace geometry"}

    # ---- reconcile storey elevations with GEOMETRY: some exports put the model
    # at site datum (sea level ≈ 500 m) while the Elevation attribute says 3.0 —
    # bands, cuts and floor filters must follow where the geometry actually is
    by_storey_z = {}
    for r in rooms:
        if r.get("storey"):
            by_storey_z.setdefault(r["storey"], []).append(r["_zmin"])
    for nm, zs in by_storey_z.items():
        zs.sort()
        med = zs[len(zs) // 2]
        if nm not in elev_of or abs(med - elev_of[nm]) > 1.0:
            elev_of[nm] = round(med, 3)

    # ---- storey assignment: synthesise bands from room base heights if needed
    if not elev_of:
        bands = []
        for z in sorted({round(r["_zmin"], 1) for r in rooms}):
            if not bands or z - bands[-1] > 1.5:
                bands.append(z)
        elev_of = {f"Level {i + 1}": z for i, z in enumerate(bands)}
    levels = sorted(elev_of.values())
    tops = {}
    for nm, e in elev_of.items():
        # a real storey is never 30 cm tall — Revit exports carry datum variants
        # (raw/finished floor levels) centimetres apart; the band above a storey
        # runs to the next REAL floor, not the next datum
        higher = [v for v in levels if v > e + 1.5]
        tops[nm] = min(higher) if higher else e + 3.1
    for r in rooms:
        if not r.get("storey") or r["storey"] not in elev_of:
            z = r["_zmin"]
            below = [(z - e, nm) for nm, e in elev_of.items() if e <= z + 0.6]
            r["storey"] = min(below)[1] if below else min((abs(z - e), nm) for nm, e in elev_of.items())[1]
        del r["_zmin"]

    used = {r["storey"] for r in rooms if r["furnishable"]}
    rooms = [r for r in rooms if r["furnishable"] or r["storey"] in used]
    storeys = [{"name": n, "elevation": round(elev_of[n], 3), "top": round(tops[n], 3)}
               for n in sorted(used, key=lambda n: elev_of.get(n, 0.0)) if n]
    return {"ok": True, "rooms": rooms, "categories": sorted(assets.keys()),
            "storeys": storeys}


def cmd_register_building(args):
    """Probe an uploaded IFC: is it usable as a building, how heavy is it, and is
    anything suspicious (units, rotation)? Cheap — counts + ONE test room shape."""
    import ifcopenshell
    import ifcopenshell.geom
    import numpy as np

    path = Path(args["path"])
    if not path.exists():
        return {"ok": False, "error": "file not found", "status": 404}
    try:
        f = ifcopenshell.open(str(path))
    except Exception as exc:
        return {"ok": False, "status": 400, "error": f"not a readable IFC: {exc}"}

    def _bt(t):
        try:
            return f.by_type(t)
        except Exception:
            return []

    spaces = _bt("IfcSpace")
    spaces_rep = [sp for sp in spaces if getattr(sp, "Representation", None)]
    if not spaces_rep:
        return {"ok": False, "status": 400,
                "error": "This IFC has no rooms with geometry (IfcSpace). "
                         "Export the architectural model with spaces/rooms included."}
    products_rep = sum(1 for p in _bt("IfcProduct") if getattr(p, "Representation", None))
    try:
        from ifcopenshell.util.unit import calculate_unit_scale
        unit_scale = float(calculate_unit_scale(f))
    except Exception:
        unit_scale = 1.0

    warnings = []
    # smoke-test space geometry on a few rooms: solid shape OR bbox fallback both
    # count (footprint-only exports like Schependomlaan are perfectly usable)
    import populate_building as pop
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    solid = 0
    usable = 0
    sampleWD = None
    for sp in spaces_rep[:5]:
        try:
            g = ifcopenshell.geom.create_shape(s, sp)
            v = np.array(g.geometry.verts).reshape(-1, 3)
            solid += 1
            usable += 1
            if sampleWD is None:
                W = float(v[:, 0].max() - v[:, 0].min())
                D = float(v[:, 1].max() - v[:, 1].min())
                sampleWD = (W, D)
                fc = np.array(g.geometry.faces).reshape(-1, 3)
                tri = v[fc]
                proj2 = float(np.abs((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                                     - (tri[:, 2, 0] - tri[:, 0, 0]) * (tri[:, 1, 1] - tri[:, 0, 1])).sum() / 2)
                if W * D > 1 and proj2 > 0 and (proj2 / 2) / (W * D) < 0.55:
                    warnings.append("building looks rotated or irregular — layouts may be conservative")
        except Exception:
            if pop.space_extent(sp, s, unit_scale) is not None:
                usable += 1
    if usable == 0:
        return {"ok": False, "status": 400,
                "error": "the geometry kernel can't extract any room from this IFC"}
    if solid == 0:
        warnings.append("rooms carry footprint-only geometry — using bounding boxes")
    if sampleWD and max(sampleWD) > 200:
        warnings.append("rooms measure suspiciously large — the file's units may be unusual")

    name = None
    for b in _bt("IfcBuilding") + _bt("IfcProject"):
        name = (getattr(b, "LongName", None) or b.Name or "").strip() or None
        if name:
            break
    return {"ok": True, "profile": {
        "schema": f.schema, "name": name,
        "spaces": len(spaces_rep), "storeys": len(_bt("IfcBuildingStorey")),
        "products": products_rep,
        "size_mb": round(path.stat().st_size / 1048576, 1),
        "unit_scale": unit_scale,
        "est_populate_min": max(1, round(products_rep / 300)),
        "warnings": warnings,
    }}


def cmd_prepare_building(args):
    """Background prepare after registration: build the geometry cache (obstacle
    footprints + decimated shell) so the user's FIRST populate is already fast."""
    import ifcopenshell
    import ifcopenshell.geom
    import populate_building as pop

    path = Path(args["path"])
    if not path.exists():
        return {"ok": False, "error": "file not found", "status": 404}
    f = ifcopenshell.open(str(path))
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    obstacles, doors = pop.cached_footprints(f, s, path)
    shell = pop.build_shell_cache(f, s, path)
    return {"ok": True, "obstacles": len(obstacles), "doors": len(doors),
            "shell": str(shell)}


def cmd_building_save(args):
    """Merge the current (possibly re-dragged) piece positions + shell into one GLB.
    Writes into the building's own scratch dir so two buildings never clobber."""
    import trimesh
    mov = Path(args.get("bldg_dir") or (Path(args["out_dir"]) / "bldg"))
    positions = args.get("positions", {}) or {}       # {piece_id: [x,y,z]}
    if not (mov / "shell.glb").exists():
        return {"ok": False, "error": "populate first", "status": 400}
    scene = trimesh.load(str(mov / "shell.glb"), force="scene")
    man = json.loads((mov / "furniture.json").read_text(encoding="utf-8"))
    for p in man.get("pieces", []):
        g = trimesh.load(str(mov / p["glb"]), force="mesh")
        g.apply_translation(positions.get(p["id"], p["pos"]))
        scene.add_geometry(g, node_name=p["id"])
    scene.export(str(mov / "building_final.glb"))
    return {"ok": True, "glb_name": "building_final.glb"}


def cmd_building_export_ifc(args):
    """Inject the populated furniture into a COPY of the building's own IFC — one
    downloadable BIM file (architecture + furniture) any IFC viewer can open.
    Each piece becomes an IfcFurnishingElement with real (gently decimated) mesh
    geometry at its final — possibly user-dragged — world position."""
    import numpy as np
    import trimesh
    import ifcopenshell
    import ifcopenshell.api.root
    import ifcopenshell.api.geometry
    import ifcopenshell.api.spatial
    import ifcopenshell.util.representation
    import ifcopenshell.util.unit

    src = Path(args["ifc"])
    mov = Path(args["bldg_dir"])
    positions = args.get("positions", {}) or {}       # {piece_id: [x,y,z]} viewer frame
    if not (mov / "furniture.json").exists():
        return {"ok": False, "error": "populate first", "status": 400}

    f = ifcopenshell.open(str(src))
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f) or 1.0   # project -> metres
    body = (ifcopenshell.util.representation.get_context(f, "Model", "Body", "MODEL_VIEW")
            or ifcopenshell.util.representation.get_context(f, "Model"))
    if body is None:
        return {"ok": False, "error": "building IFC has no model context", "status": 400}

    # containment target per piece: nearest storey below its base (attribute
    # elevations; mis-datum exports still view fine — containment is metadata)
    storeys = sorted(f.by_type("IfcBuildingStorey"),
                     key=lambda st: float(st.Elevation or 0))
    def storey_for(z_m):
        best = storeys[0] if storeys else None
        for st in storeys:
            if float(st.Elevation or 0) * unit_scale <= z_m + 0.5:
                best = st
        return best

    man = json.loads((mov / "furniture.json").read_text(encoding="utf-8"))
    yup_to_zup = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    added, skipped = 0, 0
    for p in man.get("pieces", []):
        try:
            m = trimesh.load(str(mov / p["glb"]), force="mesh")
            pos = positions.get(p["id"], p["pos"])    # Y-up world (same frame as save)
            m.apply_translation(pos)
            m.apply_transform(yup_to_zup)             # -> IFC Z-up world, metres
            if len(m.faces) > 800:                    # keep the BIM light: furniture
                try:                                  # in IFC is for coordination, not
                    m = m.simplify_quadric_decimation(face_count=800)   # close-up rendering
                except Exception:
                    pass
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcFurnishingElement",
                name=f"{p['category']} ({p['id']})")
            rep = ifcopenshell.api.geometry.add_mesh_representation(
                f, context=body,
                vertices=[(np.asarray(m.vertices, dtype=float) / unit_scale).tolist()],
                faces=[np.asarray(m.faces).tolist()])
            ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
            st = storey_for(float(pos[1]))
            if st is not None:
                ifcopenshell.api.spatial.assign_container(f, products=[el], relating_structure=st)
            added += 1
        except Exception:
            skipped += 1
            continue
    if added == 0:
        return {"ok": False, "error": "no furniture could be written", "status": 500}
    out = mov / "populated.ifc"
    f.write(str(out))
    return {"ok": True, "ifc_name": "populated.ifc", "furniture": added,
            "skipped": skipped, "mb": round(out.stat().st_size / 1e6, 2)}


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

    # photo->3D seats arrive in arbitrary orientations — store them UPRIGHT so
    # every consumer (thumbs, room solver, buildings) sees a level seat
    if ext == ".glb" and cat in _SEATING_CATS:
        try:
            import trimesh
            m = trimesh.load(str(dest), force="mesh")
            _canonicalize_seat_upright(m)
            m.export(str(dest))
        except Exception:
            pass

    dims = _mesh_dims(dest)                            # may be None (.ifc / unreadable)

    # C2 — render the 3D preview thumbnail once, cache it next to the asset
    thumb = None
    if ext == ".glb":
        thumb_fn = f"{uid}.thumb.png"
        if _render_thumb(dest, GEN_DIR / thumb_fn):
            thumb = thumb_fn

    # which AI made it — short badge shown in the picker (TSR/TSG/TRL2/SAM3D/SF3D/CAT)
    engine = str(args.get("engine") or "").strip().upper()[:8] or None

    item = {"id": uid, "category": cat, "glb": fn, "dims_m": dims,
            "thumb": thumb, "generated": True, "source_file": orig,
            "engine": engine}
    man = _read_gen_manifest()
    man.setdefault("items", []).append(item)
    GEN_MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")

    return {"ok": True, "item": {"id": uid, "category": cat, "dims_m": dims,
                                 "thumb": thumb, "generated": True, "engine": engine}}


def _rot_zone_offsets(zrects, cx, cz, delta_deg):
    """Rotate zone rects rigidly around the object's centre by a multiple of 90°."""
    steps = int(round(delta_deg / 90.0)) % 4
    out = list(zrects)
    for _ in range(steps):
        nxt = []
        for (zx, zz, zw, zd) in out:
            # rect corners relative to centre, rotated +90° about Y: (dx, dz) -> (dz, -dx)
            rel = [(zx - cx, zz - cz), (zx + zw - cx, zz + zd - cz)]
            pts = [(dz, -dx) for (dx, dz) in rel]
            xs = sorted(p[0] for p in pts); zs = sorted(p[1] for p in pts)
            nxt.append([cx + xs[0], cz + zs[0], xs[1] - xs[0], zs[1] - zs[0]])
        out = nxt
    return out


def cmd_update_positions(args):
    """Manual 2D-editor edits: move/rotate items in the schedule, re-validate
    (overlaps vs furniture+obstacles, circulation), rebuild scene.ifc — and,
    when rebuild=true, scene.glb too (for export after manual edits).

    args: {out_dir, positions: {id: {x, z, rotation_deg?}}, rebuild?: bool}
    """
    import build_room_scene
    import spatial_layout
    out_dir = Path(args["out_dir"])
    sched_path = out_dir / "schedule.json"
    if not sched_path.exists():
        return {"ok": False, "error": "generate a layout first", "status": 400}
    sched = json.loads(sched_path.read_text(encoding="utf-8"))
    positions = args.get("positions") or {}

    zones = sched.get("zones") or {}
    for it in sched["items"]:
        upd = positions.get(it["id"])
        if not upd:
            continue
        old_x, old_z = float(it["x"]), float(it["z"])
        old_rot = float(it.get("rotation_deg", 0))
        new_x = float(upd.get("x", old_x))
        new_z = float(upd.get("z", old_z))
        new_rot = float(upd.get("rotation_deg", old_rot))
        # zones ride rigidly with their object (rotate first, then translate)
        if it["id"] in zones:
            zr = zones[it["id"]]
            if (new_rot - old_rot) % 360:
                zr = _rot_zone_offsets(zr, old_x, old_z, new_rot - old_rot)
            zones[it["id"]] = [[round(zx + new_x - old_x, 3), round(zz + new_z - old_z, 3),
                                round(zw, 3), round(zd, 3)] for (zx, zz, zw, zd) in zr]
        it["x"], it["z"], it["rotation_deg"] = round(new_x, 3), round(new_z, 3), new_rot

    # ---- re-validate: footprint overlaps (rotation-aware AABB) ------------------
    room = sched["room"]
    obstacles = list(room.get("obstacles", [])) + list(room.get("doors", []))
    rects = {}
    for it in sched["items"]:
        if float(it.get("elevation", 0)) > 0.01:
            continue                       # on-top items don't collide on the floor
        w, d = float(it["width_m"]), float(it["depth_m"])
        if int(round(float(it.get("rotation_deg", 0)) / 90.0)) % 2 == 1:
            w, d = d, w
        rects[it["id"]] = [float(it["x"]) - w / 2, float(it["z"]) - d / 2, w, d]

    def _overlap(a, b):
        return (min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) > 0.02 and
                min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) > 0.02)

    violations = []
    ids = list(rects)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _overlap(rects[ids[i]], rects[ids[j]]):
                violations.append({"a": ids[i], "b": ids[j], "kind": "furniture"})
        for ob in obstacles:
            if _overlap(rects[ids[i]], [float(ob["x"]), float(ob["z"]),
                                        float(ob["width"]), float(ob["depth"])]):
                violations.append({"a": ids[i], "b": ob.get("kind", "obstacle"), "kind": "obstacle"})

    # ---- circulation still holds? ------------------------------------------------
    placements = [{"id": oid, "placed": True, "rect": r} for oid, r in rects.items()]
    circ = spatial_layout.check_circulation(room, placements, zones, room.get("obstacles"))

    sched["zones"] = zones
    sched_path.write_text(json.dumps(sched, indent=2), encoding="utf-8")
    try:
        import build_room_ifc
        build_room_ifc.build(out_dir)          # IFC always reflects the manual truth
    except Exception:
        pass

    rebuilt = False
    if args.get("rebuild"):
        spec_path = out_dir / "spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            build_room_scene.rebuild_from_schedule(spec, out_dir)
            rebuilt = True

    return {"ok": True, "violations": violations, "circulation": circ,
            "rebuilt": rebuilt, "zones": zones}


# The demo is the REAL pipeline with a curated pick list — real ABO meshes at
# ergonomic dimensions, workstation anchoring, people-zones, the works. (The old
# demo/scene_spec.json fossil carried misdetected names and broken scales — a
# 2.9 m "lamp" that was actually an armchair.)
_DEMO_ROOM = {"width": 8.0, "depth": 6.0, "height": 3.0, "type": "office",
              "name": "SCS Demo Office"}
_DEMO_PICKS = [
    {"category": "desk", "count": 2}, {"category": "office_chair", "count": 2},
    {"category": "monitor", "count": 2}, {"category": "lamp", "count": 1},
    {"category": "bookshelf", "count": 1}, {"category": "sofa", "count": 1},
    {"category": "coffee_table", "count": 1},
]


def cmd_delete_generated(args):
    """Remove a user-generated (OURS) item: manifest entry + its files."""
    gid = (args.get("id") or "").strip()
    if not gid.startswith("gen_"):
        return {"ok": False, "error": "invalid id", "status": 400}
    man = _read_gen_manifest()
    items = man.get("items", [])
    entry = next((e for e in items if e.get("id") == gid), None)
    if entry is None:
        return {"ok": False, "error": "not found", "status": 404}
    for fn in (entry.get("glb"), entry.get("thumb")):
        if fn:
            try:
                (GEN_DIR / fn).unlink()
            except Exception:
                pass
    man["items"] = [e for e in items if e.get("id") != gid]
    GEN_MANIFEST.write_text(json.dumps(man, indent=1), encoding="utf-8")
    return {"ok": True, "id": gid, "category": entry.get("category")}


def cmd_demo_run(args):
    """One-click demo. Default: the curated scene through the SAME layout pipeline
    users trigger. A legacy spec file is only used when explicitly requested."""
    import build_room_scene
    spec_file = args.get("spec_path")
    if spec_file and Path(spec_file).exists():
        spec = json.loads(Path(spec_file).read_text(encoding="utf-8"))
        out_dir = Path(args["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        res = build_room_scene.build(spec, out_dir)
        sched, render, floorplan = _build_outputs(out_dir)
        return {"ok": True, "feasible": res["solver"] == "ortools-cpsat",
                "solver": res["solver"], "message": "Demo scene built (from spec file).",
                "items": sched["items"], "room": sched["room"],
                "zones": sched.get("zones") or {},
                "glb": "/out/scene.glb", "ifc": "/out/scene.ifc",
                "metamodel": "/out/metamodel.json",
                "render": render, "floorplan": floorplan}
    result = cmd_layout({"room": dict(_DEMO_ROOM), "items": _DEMO_PICKS,
                         "out_dir": args["out_dir"]})
    if result.get("ok"):
        result["message"] = ("Demo office: two workstations, lounge corner — placed "
                            "ergonomically with room for people to move.")
    return result


_COMMANDS = {
    "catalog": cmd_catalog,
    "items": cmd_items,
    "layout": cmd_layout,
    "update_positions": cmd_update_positions,
    "building_rooms": cmd_building_rooms,
    "building_save": cmd_building_save,
    "building_export_ifc": cmd_building_export_ifc,
    "register_building": cmd_register_building,
    "prepare_building": cmd_prepare_building,
    "register_upload": cmd_register_upload,
    "delete_generated": cmd_delete_generated,
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
