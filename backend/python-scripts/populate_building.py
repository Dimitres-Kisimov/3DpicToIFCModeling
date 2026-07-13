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
                 "entree", "gang", "berging", "instal", "toilet", "trap", "mk",
                 # French (19-rue-Marc-Antoine-style exports)
                 "sanitaire", "san.", "douche", "vestiaire", "circulation", "dgt", "palier"]
# room-name keyword -> canonical room type (multi-language so ANY new building maps)
TYPE_KEYWORDS = {"living": "living", "lounge": "lounge", "bed": "bed", "kitchen": "kitchen",
                 "dining": "dining", "meeting": "meeting", "conference": "meeting",
                 "office": "office", "study": "office", "work": "office",
                 "wohn": "living", "schlaf": "bed", "kinder": "bed",
                 "küche": "kitchen", "kueche": "kitchen", "ess": "dining",
                 "besprechung": "meeting", "konferenz": "meeting",
                 "büro": "office", "buero": "office", "arbeits": "office",
                 "woon": "living", "slaap": "bed", "keuken": "kitchen", "eet": "dining",
                 # French: offices/labs classify as workplaces, waiting rooms as seating
                 "bureau": "office", "laboratoire": "office", "labo": "office",
                 "atelier": "office", "attente": "lounge", "accueil": "lounge",
                 "séjour": "living", "sejour": "living", "salon": "living",
                 "chambre": "bed", "dortoir": "bed", "cuisine": "kitchen",
                 "réunion": "meeting", "reunion": "meeting",
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
    "stool":        (0.42, 0.42, 0.50),
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


# Furniture colour fallbacks when a GLB carries no usable colour at all —
# plausible material tones per category (wood, fabric, plastic), not white.
_FURN_FALLBACK = {
    "sofa":          [0.42, 0.45, 0.52, 1.0],
    "bed":           [0.62, 0.58, 0.52, 1.0],
    "table":         [0.55, 0.40, 0.26, 1.0],
    "desk":          [0.52, 0.38, 0.25, 1.0],
    "coffee_table":  [0.55, 0.40, 0.26, 1.0],
    "side_table":    [0.55, 0.40, 0.26, 1.0],
    "bookshelf":     [0.48, 0.35, 0.24, 1.0],
    "cabinet":       [0.58, 0.44, 0.30, 1.0],
    "filing_cabinet": [0.48, 0.50, 0.54, 1.0],
    "office_chair":  [0.20, 0.20, 0.22, 1.0],
    "chair":         [0.45, 0.33, 0.23, 1.0],
    "lamp":          [0.82, 0.78, 0.70, 1.0],
    "mirror":        [0.72, 0.76, 0.80, 1.0],
    "planter":       [0.35, 0.48, 0.30, 1.0],
}


def _dominant_rgba(img):
    """Dominant colour of a texture image — quantised bins scored by count ×
    saturation, so a red sofa reads red (a plain mean averages to mud)."""
    try:
        im = img.convert("RGB")
        im.thumbnail((128, 128))
        q = im.quantize(colors=8)
        pal = q.getpalette()
        best, best_score = None, -1.0
        for count, idx in q.getcolors():
            r, g, b = pal[idx * 3: idx * 3 + 3]
            mx, mn = max(r, g, b), min(r, g, b)
            sat = (mx - mn) / mx if mx else 0.0
            score = count * (0.35 + sat)
            if score > best_score:
                best_score, best = score, (r, g, b)
        return [best[0] / 255.0, best[1] / 255.0, best[2] / 255.0, 1.0]
    except Exception:
        return None


def _part_rgba(g):
    """Best solid colour for one furniture submesh: a non-white authored
    baseColorFactor, else its texture's dominant colour, else SimpleMaterial
    diffuse, else the dominant vertex/face colour. None if truly colourless."""
    vis = getattr(g, "visual", None)
    mat = getattr(vis, "material", None)
    if mat is not None:
        bc = getattr(mat, "baseColorFactor", None)
        if bc is not None:
            try:
                bc = [float(c) for c in np.asarray(bc, dtype=float).ravel()[:4]]
                while len(bc) < 4:
                    bc.append(1.0)
                if max(bc) > 1.001:                      # 0-255 encoded
                    bc = [c / 255.0 for c in bc]
                if tuple(round(c, 2) for c in bc[:3]) != (1.0, 1.0, 1.0):
                    return bc
            except Exception:
                pass
        tex = getattr(mat, "baseColorTexture", None)
        if tex is None:
            tex = getattr(mat, "image", None)
        if tex is not None:
            c = _dominant_rgba(tex)
            if c:
                return c
        dif = getattr(mat, "diffuse", None)
        if dif is not None:
            try:
                d = np.asarray(dif, dtype=float).ravel()
                if d.max() > 1.001:
                    d = d / 255.0
                if tuple(round(float(c), 2) for c in d[:3]) != (1.0, 1.0, 1.0):
                    return [float(d[0]), float(d[1]), float(d[2]), 1.0]
            except Exception:
                pass
    try:
        if vis is not None and vis.kind in ("vertex", "face"):
            cols = np.asarray(vis.vertex_colors if vis.kind == "vertex" else vis.face_colors)
            u, cnt = np.unique(cols[:, :3] // 16, axis=0, return_counts=True)
            dom = (u[int(cnt.argmax())].astype(float) * 16 + 8) / 255.0
            return [float(dom[0]), float(dom[1]), float(dom[2]), 1.0]
    except Exception:
        pass
    return None


def _xform_all(combined, parts, M):
    combined.apply_transform(M)
    for p in parts:
        p.apply_transform(M)


def _rescale_parts_to_real(combined, parts, cat):
    """_rescale_to_real, applied identically to the logic mesh AND its parts."""
    t = TARGET_DIMS.get(cat)
    if not t:
        return
    e = combined.extents
    if min(e) < 1e-6:
        return
    if (e[0] - e[1]) * (t[0] - t[1]) < 0:              # aspect mismatch -> quarter turn
        _xform_all(combined, parts, trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
        e = combined.extents
    S = np.eye(4)
    S[0, 0], S[1, 1], S[2, 2] = t[0] / e[0], t[1] / e[1], t[2] / e[2]
    _xform_all(combined, parts, S)


def _load_colored_furniture(path, cat=None):
    """Load a furniture GLB as PER-MATERIAL PARTS, each baked to a solid PBR
    baseColorFactor the xeokit viewers actually render. (The old
    force='mesh' load silently dropped ALL visuals when flattening a
    multi-material GLB — the white-furniture bug; and xeokit ignores COLOR_0
    vertex colours, so baking into materials is the only path that shows up.)
    Returns (combined_for_logic, parts_for_export) in the file's own frame."""
    sc = trimesh.load(str(path))
    raw = []
    if isinstance(sc, trimesh.Trimesh):
        raw = [sc]
    else:
        for node in sc.graph.nodes_geometry:
            T, gname = sc.graph[node]
            g = sc.geometry[gname]
            if isinstance(g, trimesh.Trimesh) and len(g.faces):
                p = g.copy()
                p.apply_transform(T)
                raw.append(p)
    if not raw:
        raise ValueError(f"no mesh geometry in {path}")
    parts = []
    for p in raw:
        rgba = _part_rgba(p) or list(_FURN_FALLBACK.get(cat, [0.72, 0.68, 0.62, 1.0]))
        parts.append(_tinted(p, rgba))
    combined = parts[0].copy() if len(parts) == 1 else \
        trimesh.util.concatenate([q.copy() for q in parts])
    return combined, parts


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


def _stool_mesh_zup(h=0.50, w=0.42, d=0.42):
    """Procedural stool, Z-up — guaranteed LEVEL and chair-proportioned (the AI
    stool mesh sat tilted and undersized)."""
    parts = []
    seat = trimesh.creation.cylinder(radius=w / 2, height=0.06, sections=24)
    seat.apply_translation([0, 0, h - 0.03]); parts.append(seat)
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        leg = trimesh.creation.cylinder(radius=0.02, height=h - 0.06, sections=12)
        leg.apply_translation([sx * (w / 2 - 0.06), sy * (d / 2 - 0.06), (h - 0.06) / 2])
        parts.append(leg)
    return _tinted(trimesh.util.concatenate(parts), [0.48, 0.36, 0.27, 1.0])


_GEN_DIR = REPO / "data" / "generated_assets"


def load_generated(gid):
    """A user-generated (OURS) mesh by manifest id — usable as a building pick
    via 'gen:<id>'. Y-up GLB -> Z-up, normalised to its category's real dims so
    the ergonomics (pairing, zones, petals) treat it exactly like its category."""
    try:
        man = json.loads((_GEN_DIR / "manifest.json").read_text(encoding="utf-8"))
        e = next((x for x in man.get("items", []) if x.get("id") == gid), None)
        if not e or not (e.get("glb") or "").lower().endswith(".glb"):
            return None
        cat = e.get("category", "table")
        m, parts = _load_colored_furniture(str(_GEN_DIR / e["glb"]), cat)
        _xform_all(m, parts, trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        _rescale_parts_to_real(m, parts, cat)
        return {"category": cat, "mesh": m, "parts": parts}
    except Exception:
        return None


def load_assets():
    man = json.load(open(LIB / "manifest.json", encoding="utf-8"))["assets"]
    by_cat = {}
    for a in man:
        by_cat.setdefault(a["category"], a)
    out = {}
    for cat, a in by_cat.items():
        try:
            mesh, parts = _load_colored_furniture(str(LIB / a["glb"]), cat)
            _rescale_parts_to_real(mesh, parts, cat)
            out[cat] = {"mesh": mesh, "parts": parts, "ifc": a["ifc_class"]}
        except Exception:
            pass
    # on-desk electronics: procedural (the AI asset library has none) — placed ON
    # desks, screens facing the chair, exactly like the room builder
    out.setdefault("monitor", {"mesh": _monitor_mesh_zup(), "ifc": "IfcAudioVisualAppliance"})
    out.setdefault("laptop", {"mesh": _laptop_mesh_zup(), "ifc": "IfcAudioVisualAppliance"})
    out["stool"] = {"mesh": _stool_mesh_zup(), "ifc": "IfcFurniture"}   # level, chair-class

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
                m, parts = _load_colored_furniture(glb, cat)
                _xform_all(m, parts, rotx90)           # ABO GLBs are Y-up; assets are Z-up
                _rescale_parts_to_real(m, parts, cat)
                ifc = _catalog.CATALOG_META.get(cat, ("IfcFurniture",))[0]
                out[cat] = {"mesh": m, "parts": parts, "ifc": ifc}
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


def _rot2(deg):
    """2×2 CCW rotation matrix for XY plan coordinates."""
    r = np.radians(deg)
    c, s_ = np.cos(r), np.sin(r)
    return np.array([[c, -s_], [s_, c]])


def detect_building_theta(f, s):
    """Dominant wall orientation in degrees, in (-45, 45]. Buildings modelled
    ROTATED in world coordinates (e.g. the rue-Marc-Antoine export: every wall
    at 60.4°) break every axis-aligned assumption — room bboxes inflate into
    the walls and obstacle rects go fat, so furniture lands inside walls.
    The populate solves in a de-rotated local frame instead; 0.0 means the
    building is already axis-aligned and nothing changes."""
    import collections
    angs = []
    walls = list(f.by_type("IfcWallStandardCase")) or list(f.by_type("IfcWall"))
    for w in walls[:24]:
        try:
            g = ifcopenshell.geom.create_shape(s, w)
            v = np.array(g.geometry.verts).reshape(-1, 3)[:, :2]
            c = v - v.mean(0)
            _val, vec = np.linalg.eigh(c.T @ c)
            a = np.degrees(np.arctan2(vec[1, -1], vec[0, -1])) % 90.0
            angs.append(round(a * 2) / 2)                  # 0.5° bins
        except Exception:
            pass
    if not angs:
        return 0.0
    a, n = collections.Counter(angs).most_common(1)[0]
    if n < max(3, len(angs) // 3):
        return 0.0                                          # no dominant direction
    if a > 45.0:
        a -= 90.0
    return 0.0 if abs(a) < 1.0 else float(a)


def space_extent(sp, s, unit_scale=1.0, rot=None):
    """Plan bbox (x0, x1, y0, y1, zmin) in METRES for an IfcSpace, in the
    building-local frame (rot = world→local 2×2, None for axis-aligned) — via
    solid geometry when the kernel can process it, else the space's
    IfcBoundingBox (footprint-only exports like Schependomlaan). Raw attributes
    are project units, hence unit_scale; create_shape output is already metres."""
    try:
        g = ifcopenshell.geom.create_shape(s, sp)
        v = np.array(g.geometry.verts).reshape(-1, 3)
        if len(v):
            xy = v[:, :2] @ rot.T if rot is not None else v[:, :2]
            poly = None
            try:                    # true footprint — non-rectangular rooms
                from shapely.geometry import Polygon
                from shapely.ops import unary_union
                fc = np.array(g.geometry.faces).reshape(-1, 3)
                tris = []
                for t in fc:        # vertical faces project to ~zero area and drop out
                    p = Polygon(xy[t])
                    if p.is_valid and p.area > 1e-4:
                        tris.append(p)
                if tris:
                    poly = unary_union(tris).buffer(0)
            except Exception:
                poly = None
            return (float(xy[:, 0].min()), float(xy[:, 0].max()),
                    float(xy[:, 1].min()), float(xy[:, 1].max()),
                    float(v[:, 2].min()), poly)
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
                    org = np.array(list(item.Corner.Coordinates[:3]), dtype=float)
                    dims = np.array([float(item.XDim), float(item.YDim), float(item.ZDim)])
                    corners = []                 # all 8 corners — the box may be rotated
                    for dx in (0, 1):
                        for dy in (0, 1):
                            for dz in (0, 1):
                                p = m4 @ np.append(org + dims * [dx, dy, dz], 1.0)
                                corners.append(p[:3])
                    corners = np.array(corners) * float(unit_scale)
                    xy = corners[:, :2] @ rot.T if rot is not None else corners[:, :2]
                    return (float(xy[:, 0].min()), float(xy[:, 0].max()),
                            float(xy[:, 1].min()), float(xy[:, 1].max()),
                            float(corners[:, 2].min()), None)
    except Exception:
        pass
    return None


def footprint_rects(f, s, types, rot=None):
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
                xy = v[:, :2] @ rot.T if rot is not None else v[:, :2]
                rects.append((float(xy[:, 0].min()), float(xy[:, 0].max()),
                              float(xy[:, 1].min()), float(xy[:, 1].max()),
                              float(v[:, 2].min()), float(v[:, 2].max()), t))
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
CACHE_VERSION = "v6"          # bump when the cached artefacts change shape (v6: walk-through openings)


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
            try:                            # trimesh 4.x: keyword-only face_count
                tm = tm.simplify_quadric_decimation(face_count=20000)
            except Exception:
                pass
        out.append(_tinted(tm, rgba))
    return out


def cached_footprints(f, s, ifc_path):
    """Obstacle + door plan rects (building-local frame) + the building's world
    rotation theta, disk-cached. Rooms, obstacles and the solver all work in the
    de-rotated local frame; placements rotate back by theta at export."""
    d = geometry_cache_dir(ifc_path)
    fp = d / "footprints.json"
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return ([tuple(r) for r in data["obstacles"]],
                    [tuple(r) for r in data["doors"]],
                    float(data.get("theta", 0.0)))
        except Exception:
            pass
    theta = detect_building_theta(f, s)
    rot = _rot2(-theta) if theta else None
    obstacles = footprint_rects(f, s, OBSTACLE_TYPES, rot)
    doors = footprint_rects(f, s, ["IfcDoor"], rot)
    # walk-through wall openings WITHOUT a door object (archways, passages):
    # floor-level sill + human height + door-like width -> same keep-clear as a
    # door, so furniture never blocks the walking path through a wall gap
    for (ox0, ox1, oy0, oy1, oz0, oz1, _t) in footprint_rects(f, s, ["IfcOpeningElement"], rot):
        w = max(ox1 - ox0, oy1 - oy0)
        if oz1 - oz0 >= 1.4 and 0.6 <= w <= 3.0:
            doors.append((ox0, ox1, oy0, oy1, oz0, oz1, "IfcOpeningElement"))
    try:
        fp.write_text(json.dumps({"obstacles": obstacles, "doors": doors,
                                  "theta": theta}), encoding="utf-8")
    except Exception:
        pass
    return obstacles, doors, theta


# IFC element type -> human keep-out kind (A3b)
_KIND = {"IfcColumn": "column", "IfcWall": "wall", "IfcWallStandardCase": "wall",
         "IfcBeam": "beam", "IfcMember": "beam", "IfcStair": "stair",
         "IfcStairFlight": "stair", "IfcRailing": "railing"}


def extract_room_obstacles(obstacle_rects, door_rects, x0, x1, y0, y1, fz=None):
    """A3b — every fixed building element intruding into the room [x0..x1]×[y0..y1]
    as a LABELED keep-out rectangle relative to the room origin:
        [{"x","z","width","depth","kind": column|wall|beam|stair|railing|door}]
    Rects carry z-ranges: only elements at THIS room's storey count — projecting
    all storeys flat buried multi-storey rooms under upper-floor walls/stairs.
    Same-kind overlapping rects are merged; the solver treats obstacles pairwise, so
    cross-kind overlaps (a beam inside a wall) are harmless. Used by the auto-layout
    solver AND (via schedule data) the manual 2D editor."""
    def at_storey(z0, z1):
        return fz is None or (z0 < fz + 2.2 and z1 > fz + 0.05)
    keepouts = []
    for (ex0, ex1, ey0, ey1, ez0, ez1, t) in obstacle_rects:
        if not at_storey(ez0, ez1):
            continue
        ix0, ix1, iy0, iy1 = max(ex0, x0), min(ex1, x1), max(ey0, y0), min(ey1, y1)
        if ix1 - ix0 > 0.04 and iy1 - iy0 > 0.04:
            # boundary walls too: when the space geometry runs to a wall's
            # centreline (French/Dutch exports), the intruding half-thickness
            # MUST be blocked or furniture is placed inside the wall
            keepouts.append({"x": ix0 - x0, "z": iy0 - y0, "width": ix1 - ix0,
                             "depth": iy1 - iy0, "kind": _KIND.get(t, "fixed")})
    for (dx0, dx1, dy0, dy1, dz0, dz1, _t) in door_rects:  # door keep-clear (egress)
        if not at_storey(dz0, dz1):
            continue
        if fz is not None and dz0 > fz + 0.5:
            continue                        # sill above floor = window, not a walking path
        if dx1 > x0 and dx0 < x1 and dy1 > y0 and dy0 < y1:
            cx, cy = (dx0 + dx1) / 2 - x0, (dy0 + dy1) / 2 - y0
            keepouts.append({"x": max(0, cx - 0.6), "z": max(0, cy - 0.6),
                             "width": 1.2, "depth": 1.2, "kind": "door"})

    # walking paths through WALL GAPS with no IFC entity at all (two separate
    # wall segments with a passage between them): scan each room edge — where
    # an otherwise-walled edge has an uncovered span of door-like width,
    # block a corridor-width keep-clear in front of it
    walls = [(ex0, ex1, ey0, ey1) for (ex0, ex1, ey0, ey1, ez0, ez1, t) in obstacle_rects
             if t.startswith("IfcWall") and at_storey(ez0, ez1)]

    def _gap_spans(intervals, lo, hi):
        iv = sorted([max(lo, a), min(hi, b)] for a, b in intervals if b > lo and a < hi)
        merged = []
        for a, b in iv:
            if merged and a <= merged[-1][1] + 0.08:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        cov = sum(b - a for a, b in merged)
        if cov < 0.4 * (hi - lo):
            return []                       # barely-walled edge: not a wall with a gap
        return [(b1, a2) for (a1, b1), (a2, b2) in zip(merged, merged[1:])
                if 0.65 <= a2 - b1 <= 2.6]  # human passage widths only

    BAND, DEPTH = 0.35, 1.1
    for edge in ("S", "N", "W", "E"):
        if edge in ("S", "N"):
            ey = y0 if edge == "S" else y1
            spans = _gap_spans([(w[0], w[1]) for w in walls
                                if w[3] > ey - BAND and w[2] < ey + BAND], x0, x1)
            for (g0, g1) in spans:
                keepouts.append({"x": g0 - x0, "z": (ey - y0) if edge == "N" and ey - DEPTH > y0 else 0.0,
                                 "width": g1 - g0, "depth": DEPTH, "kind": "door"})
                if edge == "N":
                    keepouts[-1]["z"] = max(0.0, y1 - DEPTH - y0)
        else:
            ex = x0 if edge == "W" else x1
            spans = _gap_spans([(w[2], w[3]) for w in walls
                                if w[1] > ex - BAND and w[0] < ex + BAND], y0, y1)
            for (g0, g1) in spans:
                keepouts.append({"x": 0.0 if edge == "W" else max(0.0, x1 - DEPTH - x0),
                                 "z": g0 - y0, "width": DEPTH, "depth": g1 - g0, "kind": "door"})

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
    obstacle_rects, door_rects, theta = cached_footprints(f, s, args.ifc)
    rot_wl = _rot2(-theta) if theta else None      # world -> local (solve frame)
    rot_lw = _rot2(theta) if theta else None       # local -> world (export)

    def to_world_xy(lx, ly):
        if rot_lw is None:
            return lx, ly
        w = rot_lw @ np.array([lx, ly], dtype=float)
        return float(w[0]), float(w[1])

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
    seen_rooms = set()          # duplicate IfcSpace shells of the SAME room collapse
    for sp in f.by_type("IfcSpace"):
        name = sp.LongName or sp.Name or ""
        explicit = picks.get(name, picks.get((name or "").strip()))
        rt = room_type(name)
        if explicit is None and rt is None:                 # not furnishable + not picked
            continue
        ext = space_extent(sp, s, unit_scale, rot_wl)
        if ext is None:
            continue
        x0, x1, y0, y1, fz = ext[:5]
        room_poly = ext[5] if len(ext) > 5 else None
        key = (name.strip(), round(x0, 1), round(y0, 1), round(fz, 1))
        if key in seen_rooms:
            continue            # exact duplicate shell — furnishing it twice stacks furniture
        seen_rooms.add(key)
        W, D = x1 - x0, y1 - y0
        if W < 1.2 or D < 1.2:
            continue

        # 2) choose furniture: explicit picks (may include the user's OWN
        # generated meshes as 'gen:<id>'), else a space-aware smart set
        raw_picks = explicit if explicit is not None else smart_furnish(rt, W, D, assets)
        cats, custom_mesh, custom_parts = [], {}, {}
        for ent in raw_picks:
            if isinstance(ent, str) and ent.startswith("gen:"):
                info = load_generated(ent[4:])
                if info:
                    cats.append(info["category"])
                    custom_mesh[len(cats) - 1] = info["mesh"]
                    custom_parts[len(cats) - 1] = info.get("parts") or [info["mesh"]]
            elif ent in assets:
                cats.append(ent)
        if not cats:
            continue

        def mesh_of(idx):
            return custom_mesh.get(idx, assets[cats[idx]]["mesh"])

        def parts_of(idx):
            if idx in custom_parts:
                return custom_parts[idx]
            a = assets[cats[idx]]
            return a.get("parts") or [a["mesh"]]

        # 3) A3b — labeled fixed obstacles (columns/walls/beams/stairs) + door keep-clear
        keepouts = extract_room_obstacles(obstacle_rects, door_rects, x0, x1, y0, y1, fz)

        # 3b) non-rectangular rooms (L-shaped, internal voids): block everything
        # inside the bbox that is OUTSIDE the space's true footprint, as column
        # strips — otherwise furniture is placed in the void / the next room over
        if room_poly is not None and room_poly.area > 1.0:
            try:
                from shapely.geometry import box as _sbox
                bboxp = _sbox(x0, y0, x1, y1)
                if room_poly.area < bboxp.area * 0.985:
                    comp = bboxp.difference(room_poly.buffer(0.02))
                    step = 0.6
                    for cx0 in np.arange(x0, x1, step):
                        col = comp.intersection(_sbox(cx0, y0, min(cx0 + step, x1), y1))
                        pieces = getattr(col, "geoms", [col]) if not col.is_empty else []
                        for cp in pieces:
                            bx0, by0, bx1, by1 = cp.bounds
                            if bx1 - bx0 >= 0.05 and by1 - by0 >= 0.05:
                                keepouts.append({"x": bx0 - x0, "z": by0 - y0,
                                                 "width": bx1 - bx0, "depth": by1 - by0,
                                                 "kind": "void"})
            except Exception:
                pass

        # 4) solver objects — with the room-builder's HUMAN layer: small seating
        # pairs with a worksurface (its pull-out space is reserved in the solve;
        # afterwards the chair is placed in front of it, rotated to FACE it)
        import rule_packs
        GAP = 0.12
        ext_of = {i: mesh_of(i).extents for i, c in enumerate(cats)}
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

        objs, meshmap, partsmap, expand = [], {}, {}, {}
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
            entry = {"id": oid, "category": cat, "width": w_ + 2 * ring,
                     "depth": float(d_ + extra_d + 2 * ring), "height": float(e[2])}
            if ring > 0:
                entry["prefer"] = "center"   # a stool-ringed table is social — keep it open
            objs.append(entry)
            meshmap[oid] = mesh_of(i)
            partsmap[oid] = parts_of(i)
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
                               "mesh": meshmap[oid], "parts": partsmap.get(oid),
                               "zones": zones_room.get(oid)})
            ci = info.get("child")
            if ci is not None:
                ccat = cats[ci]
                cmesh = mesh_of(ci)
                ce = ext_of[ci]
                off = info["d_par"] / 2.0 + GAP + float(ce[1]) / 2.0
                ccx, ccz = acx + fx * off, acz + fzv * off
                fwd = _chair_forward_xy(cmesh)
                import math as _math
                cyaw = _math.degrees(_math.atan2(acz - ccz, acx - ccx)
                                     - _math.atan2(fwd[1], fwd[0]))
                room_items.append({"oid": f"{ccat}-{ci}", "cat": ccat,
                                   "cx": ccx, "cz": ccz, "yaw": cyaw, "mate": oid,
                                   "mesh": cmesh, "parts": parts_of(ci), "zones": None})
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
                    sfwd = _chair_forward_xy(mesh_of(si))
                    syaw = _math.degrees(_math.atan2(acz - sz, acx - sx)
                                         - _math.atan2(sfwd[1], sfwd[0]))
                    room_items.append({"oid": f"{scat}-{si}", "cat": scat,
                                       "cx": sx, "cz": sz, "yaw": syaw,
                                       "mesh": mesh_of(si), "parts": parts_of(si),
                                       "zones": None})

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
                                   "mesh": mesh_of(ti), "parts": parts_of(ti),
                                   "zones": None, "elev": par_h})

        boxes, room_cats = [], []
        for it in room_items:
            m = it["mesh"]
            parts = it.get("parts") or [m]
            cx, cz, yaw = it["cx"], it["cz"], it["yaw"]
            wx, wy = to_world_xy(x0 + cx, y0 + cz)   # solve frame -> true world
            cat = it["cat"]
            yaw = yaw + theta                        # de-rotated solve frame -> world
            Ryaw = (trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 0, 1])
                    if yaw else None)
            if movdir is not None:
                # export the piece centred at footprint origin (base at 0), Y-up; the viewer positions
                # it — so each piece is a separate, movable object (drag-to-reposition).
                piece = m.copy()
                if Ryaw is not None:
                    piece.apply_transform(Ryaw)
                pb = piece.bounds
                # true rotated footprint (works for facing angles, not just 90° steps)
                bex, bey = float(pb[1][0] - pb[0][0]), float(pb[1][1] - pb[0][1])
                tvec = [-(pb[0][0] + pb[1][0]) / 2, -(pb[0][1] + pb[1][1]) / 2, -pb[0][2]]
                rotx = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])  # Z-up->Y-up
                psc = trimesh.Scene()
                for kk, part in enumerate(parts):     # parts carry the colours
                    p2 = part.copy()
                    if Ryaw is not None:
                        p2.apply_transform(Ryaw)
                    p2.apply_translation(tvec)
                    p2.apply_transform(rotx)
                    psc.add_geometry(p2, node_name=f"p{kk}")
                gname = f"piece_{placed}.glb"
                psc.export(str(movdir / gname))
                pid = f"{cat}-{placed}"
                elev = float(it.get("elev") or 0.0)
                movable.append({"id": pid, "room": name, "category": cat, "glb": gname,
                                "pos": [round(wx, 3), round(fz + elev, 3), round(-wy, 3)],  # Y-up world
                                "dims": [round(bex, 3), round(bey, 3)],
                                "elev": round(elev, 3)})
                if it.get("zones"):
                    # people-space halos, world XY — drawn by the 2D floor plan
                    # (rotated buildings: centre rotated back, extents kept)
                    zr = []
                    for (zx, zz, zw, zd) in it["zones"]:
                        zcx, zcy = to_world_xy(x0 + zx + zw / 2, y0 + zz + zd / 2)
                        zr.append([round(zcx - zw / 2, 3), round(zcy - zd / 2, 3),
                                   round(zw, 3), round(zd, 3)])
                    zones_map[pid] = zr
                if elev <= 0.01:            # on-desk items don't join floor clash boxes
                    boxes.append(((wx - bex / 2, wx + bex / 2, wy - bey / 2, wy + bey / 2),
                                  it["oid"], it.get("mate")))
            else:
                g2 = m.copy()
                if Ryaw is not None:
                    g2.apply_transform(Ryaw)
                b = g2.bounds
                elev = float(it.get("elev") or 0.0)   # on-desk items sit at desk-top height
                tvec = [wx - (b[0][0] + b[1][0]) / 2, wy - (b[0][1] + b[1][1]) / 2,
                        fz + elev - b[0][2]]
                for kk, part in enumerate(parts):     # parts carry the colours
                    p2 = part.copy()
                    if Ryaw is not None:
                        p2.apply_transform(Ryaw)
                    p2.apply_translation(tvec)
                    scene.add_geometry(p2, node_name=f"{name}-{cat}-{placed}-p{kk}")
                g2.apply_translation(tvec)
                fb = g2.bounds
                if float(it.get("elev") or 0.0) <= 0.01:   # on-desk items sit above, not clashes
                    boxes.append(((fb[0][0], fb[1][0], fb[0][1], fb[1][1]),
                                  it["oid"], it.get("mate")))
            room_cats.append(cat)
            placed += 1
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (a, aid, am), (b, bid, bm) = boxes[i], boxes[j]
                if am == bid or bm == aid:
                    continue                # a chair tucked under ITS OWN desk is ergonomic, not a clash
                ax0, ax1, ay0, ay1 = a; bx0, bx1, by0, by1 = b
                if min(ax1, bx1) - max(ax0, bx0) > 0.02 and min(ay1, by1) - max(ay0, by0) > 0.02:
                    clashes += 1
        schedule.append({"room": name, "type": rt or "picked", "area_m2": round(W * D, 1),
                         "placed": len(room_cats), "items": room_cats,
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
