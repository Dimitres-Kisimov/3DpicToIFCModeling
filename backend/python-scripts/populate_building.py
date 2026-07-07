"""populate_building.py — populate a REAL architectural building IFC with furniture, ergonomically.

For each IfcSpace (room) it:
  1. reads the room's real footprint + floor level + measures its area,
  2. SMART-SELECTS a sensible, fitting furniture set for that room's TYPE + SIZE (space-aware:
     a small bedroom gets a bed; a big open office gets ~area/6.5 workstations; etc.) — or uses
     the caller's explicit picks,
  3. extracts the OBSTACLES that intrude into the room (internal/party walls, beams, members,
     columns, stairs, railings) as keep-out rectangles, plus door keep-clear zones,
  4. runs the CP-SAT ergonomic solver (spatial_layout + rule_packs: Neufert/Panero/ADA clearances,
     circulation, no-overlap) to place the furniture AROUND the obstacles with no clashes,
  5. merges the placed furniture with the building's empty shell into one populated GLB.

    python populate_building.py <building.ifc> <out.glb> [--picks picks.json]
    picks.json:  {"Living Room": ["sofa","table","lamp"], "Bedroom 1": ["bed","cabinet"], ...}

Coordinates: IFC is Z-up (floor = XY, Z = vertical); assets are Z-up + real-scaled, so furniture
drops in with a yaw-only rotation. The final scene is rotated to Y-up for the viewer.
"""
from __future__ import annotations
import sys, json, os, argparse
from pathlib import Path
import numpy as np
import trimesh
import ifcopenshell, ifcopenshell.geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spatial_layout

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "deliverable" / "asset_library"

SKIP_KEYWORDS = ["bath", "foyer", "hall", "stair", "utility", "roof", "closet", "wc", "corridor",
                 # German (SCS buildings will be German)
                 "bad", "flur", "diele", "treppe", "abstell", "technik", "garderobe",
                 # Dutch (Schependomlaan-style housing exports)
                 "entree", "gang", "berging", "instal", "toilet", "trap", "mk"]
# room-name keyword -> canonical room type (multi-language so ANY new building maps)
TYPE_KEYWORDS = {"living": "living", "lounge": "lounge", "bed": "bed", "kitchen": "kitchen",
                 "dining": "dining", "meeting": "meeting", "conference": "meeting",
                 "office": "office", "study": "office", "work": "office",
                 "wohn": "living", "schlaf": "bed", "kinder": "bed",
                 "küche": "kitchen", "kueche": "kitchen", "ess": "dining",
                 "besprechung": "meeting", "konferenz": "meeting",
                 "büro": "office", "buero": "office", "arbeits": "office",
                 "woon": "living", "slaap": "bed", "keuken": "kitchen", "eet": "dining",
                 "room": "living", "zimmer": "living", "kamer": "living"}
# structural element types that cut up a room and must be avoided
OBSTACLE_TYPES = ["IfcColumn", "IfcWall", "IfcWallStandardCase", "IfcBeam", "IfcMember",
                  "IfcStair", "IfcStairFlight", "IfcRailing"]


def _kw_hit(name, kw):
    """Keyword match that respects word starts for SHORT keywords: 'Schlafzimmer'
    still hits 'schlaf' (German compounds need substrings), but 'Dressing' must
    not hit 'ess' and English text must not hit German 'bad'."""
    i = name.find(kw)
    if i < 0:
        return False
    if len(kw) >= 5:
        return True
    return i == 0 or not name[i - 1].isalpha()


def classify_room(name):
    """'skip' (service space), a canonical room type, or None (unknown name —
    e.g. 'Zimmer 1.02' / 'Raum 5' / '101'). Unknown ≠ unusable: the UI lets the
    user furnish unknown rooms with explicit picks; keywords only drive defaults."""
    n = (name or "").lower()
    for k in SKIP_KEYWORDS:
        if _kw_hit(n, k):
            return "skip"
    for kw, t in TYPE_KEYWORDS.items():
        if _kw_hit(n, kw):
            return t
    return None


def room_type(name):
    """Canonical room type from the IFC room name, or None (service space or unknown)."""
    c = classify_room(name)
    return None if c in ("skip", None) else c


def smart_furnish(rt, W, D, assets):
    """Space-aware: a sensible, FITTING furniture set for a room of this type + size (metres).

    Quantities scale with area so a small room isn't overfilled and a large one isn't bare.
    Neufert ~6.5 m²/workstation drives office density; seating/tables scale with area."""
    area = W * D
    items = []
    if rt == "living":
        items += ["sofa"]
        if area > 12: items += ["table"]           # coffee table
        if area > 10: items += ["lamp"]
        if area > 22: items += ["bookshelf"]
    elif rt == "lounge":
        items += ["sofa"] + (["sofa"] if area > 16 else [])
        items += ["stool"] * min(4, max(1, int(area / 8)))
        if area > 12: items += ["lamp"]
    elif rt == "bed":
        items += ["bed"]
        if area > 9:  items += ["cabinet"]         # wardrobe
        if area > 12: items += ["lamp"]
        if area > 17: items += ["desk", "office_chair"]   # study nook in large bedrooms
    elif rt == "kitchen":
        items += ["cabinet"] * min(3, max(1, int(area / 6)))
        if area > 10: items += ["table"]
    elif rt == "office":
        for _ in range(min(8, max(1, int(area / 6.5)))):  # ~6.5 m²/workstation (Neufert)
            items += ["desk", "office_chair", "monitor"]
        if area > 15: items += ["cabinet"]
        if area > 22: items += ["bookshelf"]
    elif rt == "dining":
        items += ["table"] + ["chair"] * min(8, max(2, int(area / 3)))
    elif rt == "meeting":
        items += ["table"] + ["office_chair"] * min(10, max(2, int(area / 2.5)))
    return [c for c in items if c in assets]


# Real-world target dimensions per category — (width, depth, height) in metres,
# Neufert / typical retail sizes. The AI-generated library meshes come out at an
# arbitrary scale (the raw "bed" measured 0.70×0.74 m — nightstand-sized), so every
# asset is normalised to its category's real footprint at load time.
TARGET_DIMS = {
    "bed":          (1.60, 2.05, 0.55),   # double bed
    "bookshelf":    (0.90, 0.35, 1.85),
    "cabinet":      (1.20, 0.60, 1.80),   # wardrobe-class (bedrooms + kitchens)
    "chair":        (0.45, 0.52, 0.90),   # dining chair
    "desk":         (1.40, 0.70, 0.74),
    "lamp":         (0.40, 0.40, 1.60),   # floor lamp
    "office_chair": (0.60, 0.60, 1.10),
    "sofa":         (2.00, 0.90, 0.85),   # 2-3 seater
    "stool":        (0.40, 0.40, 0.60),
    "table":        (1.10, 0.80, 0.75),
    # ABO-borrowed categories (see load_assets)
    "coffee_table":   (1.10, 0.60, 0.45),
    "side_table":     (0.55, 0.55, 0.55),
    "filing_cabinet": (0.45, 0.60, 1.32),
    "planter":        (0.40, 0.40, 0.90),
    "mirror":         (0.60, 0.15, 1.70),  # floor mirror
}

# floor-standing categories the AI library lacks — borrowed from the SAME ABO
# catalog the room builder uses, so both parts of the app offer them. Wall-
# mounted decor (clock, picture_frame) stays room-only: the building path has
# no wall-mounting logic yet and clocks don't belong on floors.
_ABO_BORROW = ["coffee_table", "side_table", "filing_cabinet", "planter", "mirror"]


def _rescale_to_real(mesh, cat):
    """Normalise a Z-up mesh to its category's real-world (W, D, H). If the mesh was
    modelled sideways (footprint aspect opposite to the target's, e.g. the desk with
    depth > width), rotate it 90° about Z first so scaling doesn't distort it."""
    t = TARGET_DIMS.get(cat)
    if not t:
        return mesh
    e = mesh.extents
    if min(e) < 1e-6:
        return mesh
    if (e[0] - e[1]) * (t[0] - t[1]) < 0:              # aspect mismatch -> quarter turn
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        e = mesh.extents
    S = np.eye(4)
    S[0, 0], S[1, 1], S[2, 2] = t[0] / e[0], t[1] / e[1], t[2] / e[2]
    mesh.apply_transform(S)
    return mesh


def build_shell_cache(f, s, ifc_path, force=False):
    """Build (once) the building's empty shell as a Y-up GLB in the geometry cache.
    This is the dominant populate cost (create_shape for every product) — caching
    it makes every populate after the first solver-only. Heavy meshes are gently
    decimated per-mesh so the browser never loads a monster GLB."""
    d = geometry_cache_dir(ifc_path)
    out = d / "shell.glb"
    if out.exists() and not force:
        return str(out)
    scene = trimesh.Scene()
    n_shell = 0
    try:
        prods = f.by_type("IfcProduct")
    except Exception:
        prods = []
    for prod in prods:
        if prod.is_a() in {"IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
                           "IfcSpace", "IfcOpeningElement"} or not getattr(prod, "Representation", None):
            continue
        try:
            sh = ifcopenshell.geom.create_shape(s, prod)
            for tm in _colored_product_meshes(sh, prod):    # authored IFC colours + palette
                scene.add_geometry(tm, node_name=f"shell-{n_shell}")
                n_shell += 1
        except Exception:
            pass
    scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # -> Y-up
    tmp = d / "shell.tmp.glb"
    scene.export(str(tmp))
    tmp.replace(out)                             # atomic under concurrent jobs
    (d / "shell.meta.json").write_text(json.dumps({"elements": n_shell}), encoding="utf-8")
    return str(out)


def _monitor_mesh_zup(h=0.45, w=0.55, d=0.18):
    """Procedural monitor, Z-up; the user/screen side is local +Y."""
    parts = []
    screen = trimesh.creation.box(extents=[w, 0.03, h * 0.7])
    screen.apply_translation([0, 0, h * 0.5 + 0.05]); parts.append(screen)
    stand = trimesh.creation.box(extents=[w * 0.2, min(d, 0.10), 0.04])
    stand.apply_translation([0, 0, 0.02]); parts.append(stand)
    neck = trimesh.creation.cylinder(radius=0.03, height=0.05, sections=12)
    neck.apply_translation([0, 0, 0.05]); parts.append(neck)
    m = trimesh.util.concatenate(parts)
    return _tinted(m, [0.12, 0.12, 0.14, 1.0])


def _laptop_mesh_zup(h=0.25, w=0.34, d=0.24):
    """Procedural open laptop, Z-up; keyboard/user side is local +Y."""
    parts = []
    base = trimesh.creation.box(extents=[w, d, h * 0.10])
    base.apply_translation([0, 0, h * 0.05]); parts.append(base)
    screen = trimesh.creation.box(extents=[w, h * 0.05, h * 0.95])
    screen.apply_transform(trimesh.transformations.rotation_matrix(np.radians(15), [1, 0, 0]))
    screen.apply_translation([0, -d / 2 + h * 0.05, h * 0.5]); parts.append(screen)
    m = trimesh.util.concatenate(parts)
    return _tinted(m, [0.16, 0.16, 0.18, 1.0])


def load_assets():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], a)
    out = {}
    for cat, a in by_cat.items():
        try:
            mesh = _rescale_to_real(trimesh.load(str(LIB / a["glb"]), force="mesh"), cat)
            out[cat] = {"mesh": mesh, "ifc": a["ifc_class"]}
        except Exception:
            pass
    # on-desk electronics: procedural (the AI asset library has none) — placed ON
    # desks, screens facing the chair, exactly like the room builder
    out.setdefault("monitor", {"mesh": _monitor_mesh_zup(), "ifc": "IfcAudioVisualAppliance"})
    out.setdefault("laptop", {"mesh": _laptop_mesh_zup(), "ifc": "IfcAudioVisualAppliance"})

    # borrow the room builder's ABO meshes for the remaining categories, so the
    # building picker offers (almost) the same catalog as "Build a room"
    try:
        import catalog as _catalog
        rotx90 = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
        for cat in _ABO_BORROW:
            if cat in out:
                continue
            # categories without direct ABO meshes reuse a visually-similar source
            # (coffee_table -> table etc.), exactly like the room builder does
            src = cat if cat in _catalog.ABO_CATEGORIES else _catalog.MESH_BORROW.get(cat, cat)
            glb = _catalog._abo_glb(src, 0)
            if not glb:
                continue
            try:
                m = trimesh.load(glb, force="mesh")
                m.apply_transform(rotx90)              # ABO GLBs are Y-up; assets are Z-up
                m = _rescale_to_real(m, cat)
                ifc = _catalog.CATALOG_META.get(cat, ("IfcFurniture",))[0]
                out[cat] = {"mesh": m, "ifc": ifc}
            except Exception:
                pass
    except Exception:
        pass
    return out


def _chair_forward_xy(m):
    """Native forward (backrest -> seat front) of a Z-up seat mesh in XY, so the
    chair can be rotated to FACE its desk regardless of the mesh's orientation."""
    try:
        v = m.vertices
        z = v[:, 2]
        z0, z1 = float(z.min()), float(z.max())
        h = z1 - z0
        if h < 1e-6:
            return (0.0, 1.0)
        back = v[z > z0 + 0.6 * h][:, :2]
        seat = v[z < z0 + 0.5 * h][:, :2]
        if len(back) < 10 or len(seat) < 10:
            return (0.0, 1.0)
        fwd = seat.mean(axis=0) - back.mean(axis=0)
        n = float(np.hypot(fwd[0], fwd[1]))
        return (float(fwd[0] / n), float(fwd[1] / n)) if n > 1e-6 else (0.0, 1.0)
    except Exception:
        return (0.0, 1.0)


def space_extent(sp, s, unit_scale=1.0):
    """World bbox (x0, x1, y0, y1, zmin) in METRES for an IfcSpace — via solid
    geometry when the kernel can process it, else the space's IfcBoundingBox
    (footprint-only exports like Schependomlaan). Raw attributes are project
    units, hence unit_scale; create_shape output is already metres."""
    try:
        g = ifcopenshell.geom.create_shape(s, sp)
        v = np.array(g.geometry.verts).reshape(-1, 3)
        if len(v):
            return (float(v[:, 0].min()), float(v[:, 0].max()),
                    float(v[:, 1].min()), float(v[:, 1].max()), float(v[:, 2].min()))
    except Exception:
        pass
    rep = getattr(sp, "Representation", None)
    if not rep:
        return None
    try:
        import ifcopenshell.util.placement as up
        for r in rep.Representations:
            for item in r.Items:
                if item.is_a("IfcBoundingBox"):
                    m4 = np.array(up.get_local_placement(sp.ObjectPlacement))
                    lo = m4 @ np.array(list(item.Corner.Coordinates[:3]) + [1.0])
                    hi = lo[:3] + m4[:3, :3] @ np.array([float(item.XDim), float(item.YDim), float(item.ZDim)])
                    x0, x1 = sorted((float(lo[0]), float(hi[0])))
                    y0, y1 = sorted((float(lo[1]), float(hi[1])))
                    z0 = min(float(lo[2]), float(hi[2]))
                    u = float(unit_scale)
                    return (x0 * u, x1 * u, y0 * u, y1 * u, z0 * u)
    except Exception:
        pass
    return None


def footprint_rects(f, s, types):
    rects = []
    for t in types:
        try:
            prods = f.by_type(t)
        except Exception:
            prods = []                       # type absent from this schema
        for e in prods:
            if not getattr(e, "Representation", None):
                continue
            try:
                g = ifcopenshell.geom.create_shape(s, e)
                v = np.array(g.geometry.verts).reshape(-1, 3)
                rects.append((float(v[:, 0].min()), float(v[:, 0].max()),
                              float(v[:, 1].min()), float(v[:, 1].max()), t))
            except Exception:
                pass
    return rects


# ---------------------------------------------------------------------------
# Per-building geometry cache — extracting obstacles/doors and building the
# shell are the expensive parts (linear in product count) and NEVER change for
# a given IFC file. Cache them keyed by (path, mtime, size) so only the FIRST
# scan of a new building pays; repeat populates are solver-only.
# ---------------------------------------------------------------------------
CACHE_ROOT = REPO / "data" / "buildings" / "_cache"
CACHE_VERSION = "v2"          # bump when the cached artefacts change shape (v2: colored shell)


def geometry_cache_dir(ifc_path):
    import hashlib
    p = Path(ifc_path).resolve()
    st = p.stat()
    key = f"{CACHE_VERSION}_{hashlib.md5(str(p).lower().encode()).hexdigest()[:10]}_{int(st.st_mtime)}_{st.st_size}"
    d = CACHE_ROOT / key
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Shell colouring — the IFC's authored surface styles, with a professional
# BIM-viewer palette as the fallback for unstyled products.
# ---------------------------------------------------------------------------
_CLASS_PALETTE = [                      # (class prefix, [r, g, b, a])
    ("IfcWall",     [0.93, 0.90, 0.85, 1.0]),
    ("IfcSlab",     [0.80, 0.79, 0.77, 1.0]),
    ("IfcRoof",     [0.70, 0.44, 0.38, 1.0]),
    ("IfcDoor",     [0.62, 0.47, 0.32, 1.0]),
    ("IfcWindow",   [0.58, 0.74, 0.90, 0.35]),
    ("IfcPlate",    [0.58, 0.74, 0.90, 0.35]),
    ("IfcStair",    [0.66, 0.68, 0.72, 1.0]),
    ("IfcRailing",  [0.55, 0.58, 0.63, 1.0]),
    ("IfcColumn",   [0.72, 0.72, 0.74, 1.0]),
    ("IfcBeam",     [0.72, 0.72, 0.74, 1.0]),
    ("IfcCovering", [0.90, 0.89, 0.86, 1.0]),
    ("IfcMember",   [0.68, 0.70, 0.73, 1.0]),
]


def _palette_rgba(ifc_class):
    for prefix, rgba in _CLASS_PALETTE:
        if ifc_class.startswith(prefix):
            return list(rgba)
    return [0.85, 0.85, 0.86, 1.0]


def _tinted(mesh, rgba):
    try:
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=np.array(rgba, dtype=float),
                roughnessFactor=0.85, metallicFactor=0.0,
                alphaMode="BLEND" if rgba[3] < 0.999 else None,
            ))
    except Exception:
        pass
    return mesh


def _colored_product_meshes(sh, prod):
    """Split a created shape into per-material trimesh submeshes carrying the
    IFC's AUTHORED surface colours; unstyled faces get the class palette.
    Heavy submeshes are gently decimated (split first, THEN decimate)."""
    v = np.array(sh.geometry.verts).reshape(-1, 3)
    fc = np.array(sh.geometry.faces).reshape(-1, 3)
    if not len(v) or not len(fc):
        return []
    mats = list(getattr(sh.geometry, "materials", []) or [])
    try:
        mids = np.array(list(sh.geometry.material_ids), dtype=int)
    except Exception:
        mids = np.full(len(fc), -1, dtype=int)
    if len(mids) != len(fc):
        mids = np.full(len(fc), -1, dtype=int)

    fallback = _palette_rgba(prod.is_a())
    out = []
    for mid in np.unique(mids):
        faces = fc[mids == mid]
        if not len(faces):
            continue
        rgba = list(fallback)
        if mid >= 0 and mid < len(mats):
            try:
                st = mats[mid]
                d = st.diffuse
                rgba = [float(d.r), float(d.g), float(d.b),
                        1.0 - float(getattr(st, "transparency", 0.0) or 0.0)]
            except Exception:
                pass
        tm = trimesh.Trimesh(vertices=v, faces=faces)
        if len(faces) > 20000:              # per-submesh budget: heavy slabs only
            try:
                tm = tm.simplify_quadric_decimation(20000)
            except Exception:
                pass
        out.append(_tinted(tm, rgba))
    return out


def cached_footprints(f, s, ifc_path):
    """Obstacle + door world rects for the whole building, disk-cached."""
    d = geometry_cache_dir(ifc_path)
    fp = d / "footprints.json"
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return ([tuple(r) for r in data["obstacles"]],
                    [tuple(r) for r in data["doors"]])
        except Exception:
            pass
    obstacles = footprint_rects(f, s, OBSTACLE_TYPES)
    doors = footprint_rects(f, s, ["IfcDoor"])
    try:
        fp.write_text(json.dumps({"obstacles": obstacles, "doors": doors}), encoding="utf-8")
    except Exception:
        pass
    return obstacles, doors


# IFC element type -> human keep-out kind (A3b)
_KIND = {"IfcColumn": "column", "IfcWall": "wall", "IfcWallStandardCase": "wall",
         "IfcBeam": "beam", "IfcMember": "beam", "IfcStair": "stair",
         "IfcStairFlight": "stair", "IfcRailing": "railing"}


def extract_room_obstacles(obstacle_rects, door_rects, x0, x1, y0, y1):
    """A3b — every fixed building element intruding into the room [x0..x1]×[y0..y1]
    as a LABELED keep-out rectangle relative to the room origin:
        [{"x","z","width","depth","kind": column|wall|beam|stair|railing|door}]
    Same-kind overlapping rects are merged; the solver treats obstacles pairwise, so
    cross-kind overlaps (a beam inside a wall) are harmless. Used by the auto-layout
    solver AND (via schedule data) the manual 2D editor."""
    keepouts = []
    for (ex0, ex1, ey0, ey1, t) in obstacle_rects:
        ix0, ix1, iy0, iy1 = max(ex0, x0), min(ex1, x1), max(ey0, y0), min(ey1, y1)
        if ix1 - ix0 > 0.05 and iy1 - iy0 > 0.05:
            # drop the room's own perimeter walls (they are the boundary, not obstacles)
            if (ix0 > x0 + 0.25 and ix1 < x1 - 0.25) or (iy0 > y0 + 0.25 and iy1 < y1 - 0.25):
                keepouts.append({"x": ix0 - x0, "z": iy0 - y0, "width": ix1 - ix0,
                                 "depth": iy1 - iy0, "kind": _KIND.get(t, "fixed")})
    for (dx0, dx1, dy0, dy1, _t) in door_rects:            # door keep-clear (egress)
        if dx1 > x0 and dx0 < x1 and dy1 > y0 and dy0 < y1:
            cx, cy = (dx0 + dx1) / 2 - x0, (dy0 + dy1) / 2 - y0
            keepouts.append({"x": max(0, cx - 0.6), "z": max(0, cy - 0.6),
                             "width": 1.2, "depth": 1.2, "kind": "door"})

    # merge overlaps within the SAME kind so labels survive
    merged = []
    for kind in {k["kind"] for k in keepouts}:
        same = [k for k in keepouts if k["kind"] == kind]
        if len(same) > 1:
            from shapely.geometry import box as _box
            from shapely.ops import unary_union
            u = unary_union([_box(k["x"], k["z"], k["x"] + k["width"], k["z"] + k["depth"]) for k in same])
            geoms = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
            merged += [{"x": g.bounds[0], "z": g.bounds[1], "width": g.bounds[2] - g.bounds[0],
                        "depth": g.bounds[3] - g.bounds[1], "kind": kind} for g in geoms]
        else:
            merged += same
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc"); ap.add_argument("out")
    ap.add_argument("--picks", default="")
    ap.add_argument("--movable", default="")   # dir: emit shell.glb + per-piece GLBs + furniture.json
    args = ap.parse_args()

    picks = json.load(open(args.picks, encoding="utf-8")) if args.picks else {}
    f = ifcopenshell.open(args.ifc)
    s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
    try:
        from ifcopenshell.util.unit import calculate_unit_scale
        unit_scale = float(calculate_unit_scale(f))
    except Exception:
        unit_scale = 1.0
    assets = load_assets()
    movdir = Path(args.movable) if args.movable else None
    if movdir is not None:
        movdir.mkdir(parents=True, exist_ok=True)
    movable = []
    zones_map = {}                     # piece id -> [[x, y, w, d]] people-space, world XY
    obstacle_rects, door_rects = cached_footprints(f, s, args.ifc)

    scene = trimesh.Scene()
    n_shell = 0
    if movdir is not None:
        # movable (app) mode: the shell comes from the per-building geometry cache —
        # built once, reused by every later populate (repeat populates = solver-only)
        import shutil as _sh
        shell_src = Path(build_shell_cache(f, s, args.ifc))
        try:
            meta = json.loads((shell_src.parent / "shell.meta.json").read_text(encoding="utf-8"))
            n_shell = int(meta.get("elements", 0))
        except Exception:
            pass
        dest = movdir / "shell.glb"
        try:
            dest.unlink()                                          # stale link from a prior run
        except Exception:
            pass
        try:
            os.link(str(shell_src), str(dest))                     # zero-copy on same volume
        except Exception:
            _sh.copy2(str(shell_src), str(dest))
    else:
        # merged single-GLB mode: build the shell inline (furniture merges into it)
        for prod in f.by_type("IfcProduct"):
            if prod.is_a() in {"IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
                               "IfcSpace", "IfcOpeningElement"} or not getattr(prod, "Representation", None):
                continue
            try:
                sh = ifcopenshell.geom.create_shape(s, prod)
                for tm in _colored_product_meshes(sh, prod):
                    scene.add_geometry(tm, node_name=f"shell-{n_shell}")
                    n_shell += 1
            except Exception:
                pass

    placed, rooms_done, skipped_items, clashes = 0, 0, 0, 0
    schedule = []
    for sp in f.by_type("IfcSpace"):
        name = sp.LongName or sp.Name or ""
        explicit = picks.get(name, picks.get((name or "").strip()))
        rt = room_type(name)
        if explicit is None and rt is None:                 # not furnishable + not picked
            continue
        ext = space_extent(sp, s, unit_scale)
        if ext is None:
            continue
        x0, x1, y0, y1, fz = ext
        W, D = x1 - x0, y1 - y0
        if W < 1.2 or D < 1.2:
            continue

        # 2) choose furniture: explicit picks, else space-aware smart set
        if explicit is not None:
            cats = [c for c in explicit if c in assets]
        else:
            cats = smart_furnish(rt, W, D, assets)
        if not cats:
            continue

        # 3) A3b — labeled fixed obstacles (columns/walls/beams/stairs) + door keep-clear
        keepouts = extract_room_obstacles(obstacle_rects, door_rects, x0, x1, y0, y1)

        # 4) solver objects — with the room-builder's HUMAN layer: small seating
        # pairs with a worksurface (its pull-out space is reserved in the solve;
        # afterwards the chair is placed in front of it, rotated to FACE it)
        import rule_packs
        GAP = 0.12
        ext_of = {i: assets[c]["mesh"].extents for i, c in enumerate(cats)}
        chair_idx = [i for i, c in enumerate(cats)
                     if rule_packs.archetype_of(c) == "seating" and c != "stool"
                     and max(float(ext_of[i][0]), float(ext_of[i][1])) <= 0.9]
        surf_idx = [i for i, c in enumerate(cats) if rule_packs.archetype_of(c) == "worksurface"]

        # stools fan around a TABLE in a petal ring (2 opposite, 3 at 120°, ...);
        # stools with no table in the room stay free-standing (a lounge is fine)
        table_hosts = [j for j in surf_idx if cats[j] == "table"] or surf_idx
        stools_of = {}
        if table_hosts:
            for si in [i for i, c in enumerate(cats) if c == "stool"]:
                host = min(table_hosts, key=lambda j: len(stools_of.get(j, [])))
                stools_of.setdefault(host, []).append(si)
        stool_children = {si for lst in stools_of.values() for si in lst}
        pair_of = {}                        # chair index -> its worksurface index
        _PREF = {"office_chair": ["desk", "table"], "chair": ["table", "desk"]}
        for ci in chair_idx:
            order = _PREF.get(cats[ci], ["desk", "table"])
            open_surfaces = sorted(
                (j for j in surf_idx if j not in pair_of.values()),
                key=lambda j: order.index(cats[j]) if cats[j] in order else 99)
            if not open_surfaces:
                break
            pair_of[ci] = open_surfaces[0]

        # on-desk electronics ride ON a worksurface, screens facing the chair
        _TOP_SLOTS = [[0.0, -0.05], [-0.35, -0.02], [0.35, -0.02]]
        tops_of = {}                        # surface index -> [electronics indices]
        unhosted_tops = []                  # electronics with no desk/table in the room
        for ti in [i for i, c in enumerate(cats) if c in ("monitor", "laptop")]:
            hosts = sorted(surf_idx, key=lambda j: len(tops_of.get(j, [])))
            if not hosts:
                unhosted_tops.append(cats[ti])
                continue
            tops_of.setdefault(hosts[0], []).append(ti)
        top_children = {ti for lst in tops_of.values() for ti in lst}

        objs, meshmap, expand = [], {}, {}
        dropped = list(unhosted_tops)       # honest per-room "no space" report
        skipped_items += len(unhosted_tops)
        for i, cat in enumerate(cats):
            if i in pair_of or i in top_children or i in stool_children:
                continue                    # anchored child — placed after the solve
            e = ext_of[i]
            w_, d_ = float(e[0]), float(e[1])
            extra_d = 0.0
            child_i = next((c for c, par in pair_of.items() if par == i), None)
            if child_i is not None:
                ce = ext_of[child_i]
                extra_d = GAP + float(ce[1])
                w_ = max(w_, float(ce[0]))
            # a stool ring reserves a full band around the table in the solve
            ring = 0.0
            if stools_of.get(i):
                ring = GAP + max(max(float(ext_of[si][0]), float(ext_of[si][1]))
                                 for si in stools_of[i])
            if w_ + 2 * ring > W - 0.5 or d_ + extra_d + 2 * ring > D - 0.5:
                skipped_items += 1
                dropped.append(cat)
                if child_i is not None:
                    skipped_items += 1
                    dropped.append(cats[child_i])
                    pair_of.pop(child_i)
                for ti in tops_of.pop(i, []):
                    skipped_items += 1
                    dropped.append(cats[ti])
                for si in stools_of.pop(i, []):
                    skipped_items += 1
                    dropped.append(cats[si])
                continue
            oid = f"{cat}-{i}"
            objs.append({"id": oid, "category": cat, "width": w_ + 2 * ring,
                         "depth": float(d_ + extra_d + 2 * ring), "height": float(e[2])})
            meshmap[oid] = assets[cat]["mesh"]
            expand[oid] = {"extra_d": extra_d, "child": child_i,
                           "d_par": float(e[1]), "tops": tops_of.get(i, []),
                           "stools": stools_of.get(i, [])}
        if not objs:
            continue

        # fit-as-many-as-possible is native now: the solver's optional placement keeps
        # the maximum ergonomic subset and reports the rest as placed=False.
        res = spatial_layout.layout_room({"width": float(W), "depth": float(D), "height": 3.0},
                                         objs, obstacles=keepouts)
        placed_ps = [p for p in res["placements"] if p.get("placed") and p.get("position")]
        skipped_items += len(res["placements"]) - len(placed_ps)
        # solver-dropped items (and their paired chairs/electronics) join the report
        for oid in (res.get("unplaced") or []):
            dropped.append(oid.rsplit("-", 1)[0])
            info = expand.get(oid, {})
            ci = info.get("child")
            if ci is not None:
                dropped.append(cats[ci])
                skipped_items += 1
            for ti in info.get("tops", []):
                dropped.append(cats[ti])
                skipped_items += 1
            for si in info.get("stools", []):
                dropped.append(cats[si])
                skipped_items += 1
        circ = res.get("circulation") or {}
        unreachable = [oid.rsplit("-", 1)[0] for oid in (circ.get("unreachable") or [])]
        if not placed_ps:
            schedule.append({"room": name, "type": rt or "picked", "area_m2": round(W * D, 1),
                             "placed": 0, "items": [], "dropped": dropped,
                             "unreachable": unreachable})
            continue

        # resolve final per-item placements (parents pulled back to their true
        # centre; paired chairs in front of the surface, facing it)
        room_items = []
        zones_room = dict(res.get("zones") or {})
        for p in placed_ps:
            oid = p["id"]
            info = expand.get(oid, {})
            cx, cz, yaw = p["position"][0], p["position"][2], float(p["rotation"][1])
            fx, fzv = (p.get("front") or [0.0, 1.0])
            extra = float(info.get("extra_d", 0.0))
            acx, acz = cx - fx * extra / 2.0, cz - fzv * extra / 2.0
            room_items.append({"oid": oid, "cat": oid.rsplit("-", 1)[0],
                               "cx": acx, "cz": acz, "yaw": yaw,
                               "mesh": meshmap[oid], "zones": zones_room.get(oid)})
            ci = info.get("child")
            if ci is not None:
                ccat = cats[ci]
                cmesh = assets[ccat]["mesh"]
                ce = ext_of[ci]
                off = info["d_par"] / 2.0 + GAP + float(ce[1]) / 2.0
                ccx, ccz = acx + fx * off, acz + fzv * off
                fwd = _chair_forward_xy(cmesh)
                import math as _math
                cyaw = _math.degrees(_math.atan2(acz - ccz, acx - ccx)
                                     - _math.atan2(fwd[1], fwd[0]))
                room_items.append({"oid": f"{ccat}-{ci}", "cat": ccat,
                                   "cx": ccx, "cz": ccz, "yaw": cyaw,
                                   "mesh": cmesh, "zones": None})
            # stool petal ring: fan evenly around the table, each facing it
            stool_list = info.get("stools", [])
            if stool_list:
                import math as _math
                base = _math.atan2(fx, fzv)                    # start at the front
                pw = max(float(meshmap[oid].extents[0]), float(meshmap[oid].extents[1]))
                for k, si in enumerate(stool_list):
                    scat = cats[si]
                    se = ext_of[si]
                    r_ = pw / 2 + max(float(se[0]), float(se[1])) / 2 + 0.12
                    ang = base + 2 * _math.pi * k / len(stool_list)
                    sx = acx + _math.sin(ang) * r_
                    sz = acz + _math.cos(ang) * r_
                    sfwd = _chair_forward_xy(assets[scat]["mesh"])
                    syaw = _math.degrees(_math.atan2(acz - sz, acx - sx)
                                         - _math.atan2(sfwd[1], sfwd[0]))
                    room_items.append({"oid": f"{scat}-{si}", "cat": scat,
                                       "cx": sx, "cz": sz, "yaw": syaw,
                                       "mesh": assets[scat]["mesh"], "zones": None})

            # on-desk electronics: slot offsets rotated with the desk; the
            # screen (+Y local) turned toward the desk's front — i.e. the chair
            par_h = float(meshmap[oid].extents[2])             # desk/table top height
            for k, ti in enumerate(info.get("tops", [])):
                tcat = cats[ti]
                slot = _TOP_SLOTS[k % len(_TOP_SLOTS)]
                rxv, rzv = fzv, -fx                            # right-hand perpendicular
                tx = acx + slot[0] * rxv + slot[1] * fx
                tz = acz + slot[0] * rzv + slot[1] * fzv
                import math as _math
                tyaw = _math.degrees(_math.atan2(-fx, fzv))    # +Y local -> (fx, fzv)
                room_items.append({"oid": f"{tcat}-{ti}", "cat": tcat,
                                   "cx": tx, "cz": tz, "yaw": tyaw,
                                   "mesh": assets[tcat]["mesh"], "zones": None,
                                   "elev": par_h})

        boxes, room_cats = [], []
        for it in room_items:
            m = it["mesh"]
            cx, cz, yaw = it["cx"], it["cz"], it["yaw"]
            wx, wy, cat = x0 + cx, y0 + cz, it["cat"]
            if movdir is not None:
                # export the piece centred at footprint origin (base at 0), Y-up; the viewer positions
                # it — so each piece is a separate, movable object (drag-to-reposition).
                piece = m.copy()
                if yaw:
                    piece.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1]))
                pb = piece.bounds
                # true rotated footprint (works for facing angles, not just 90° steps)
                bex, bey = float(pb[1][0] - pb[0][0]), float(pb[1][1] - pb[0][1])
                piece.apply_translation([-(pb[0][0] + pb[1][0]) / 2, -(pb[0][1] + pb[1][1]) / 2, -pb[0][2]])
                piece.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # Z-up->Y-up
                gname = f"piece_{placed}.glb"
                piece.export(str(movdir / gname))
                pid = f"{cat}-{placed}"
                elev = float(it.get("elev") or 0.0)
                movable.append({"id": pid, "room": name, "category": cat, "glb": gname,
                                "pos": [round(wx, 3), round(fz + elev, 3), round(-wy, 3)],  # Y-up world
                                "dims": [round(bex, 3), round(bey, 3)],
                                "elev": round(elev, 3)})
                if it.get("zones"):
                    # people-space halos, world XY — drawn by the 2D floor plan
                    zones_map[pid] = [[round(x0 + zx, 3), round(y0 + zz, 3),
                                       round(zw, 3), round(zd, 3)]
                                      for (zx, zz, zw, zd) in it["zones"]]
                if elev <= 0.01:            # on-desk items don't join floor clash boxes
                    boxes.append((wx - bex / 2, wx + bex / 2, wy - bey / 2, wy + bey / 2))
            else:
                g2 = m.copy()
                if yaw:
                    g2.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1]))
                b = g2.bounds
                g2.apply_translation([wx - (b[0][0] + b[1][0]) / 2, wy - (b[0][1] + b[1][1]) / 2, fz - b[0][2]])
                scene.add_geometry(g2, node_name=f"{name}-{cat}-{placed}")
                fb = g2.bounds
                boxes.append((fb[0][0], fb[1][0], fb[0][1], fb[1][1]))
            room_cats.append(cat)
            placed += 1
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ax0, ax1, ay0, ay1 = boxes[i]; bx0, bx1, by0, by1 = boxes[j]
                if min(ax1, bx1) - max(ax0, bx0) > 0.02 and min(ay1, by1) - max(ay0, by0) > 0.02:
                    clashes += 1
        schedule.append({"room": name, "type": rt or "picked", "area_m2": round(W * D, 1),
                         "placed": len(boxes), "items": room_cats,
                         "dropped": dropped, "unreachable": unreachable})
        rooms_done += 1

    if movdir is not None:
        # shell.glb already linked/copied from the geometry cache
        (movdir / "furniture.json").write_text(
            json.dumps({"pieces": movable, "zones": zones_map}), encoding="utf-8")
        out_info = {"shell": "shell.glb", "movable_pieces": len(movable)}
    else:
        scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # -> Y-up
        scene.export(args.out)
        out_info = {"out": args.out, "kb": os.path.getsize(args.out) // 1024}
    print(json.dumps({"ok": True, **out_info, "shell_elements": n_shell, "rooms_populated": rooms_done,
                      "furniture_placed": placed, "items_too_big_skipped": skipped_items,
                      "furniture_furniture_clashes": clashes, "schedule": schedule}))


if __name__ == "__main__":
    main()
