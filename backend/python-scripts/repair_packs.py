"""
repair_packs.py — archetype-driven mesh repair for photo→3D output, ALL categories.

The office-chair base graft proved the recipe: keep what the generator does well
(body shape, colour), rebuild what single-view reconstruction structurally cannot
(thin supports, symmetry, contact). This module generalizes that recipe: every
CLIP label the app produces resolves to a REPAIR archetype, and each archetype
selects which universal fixes run and how hard.

Repair archetypes (geometry — distinct from rule_packs' placement archetypes):
  legged       tables/desks/stools/plain chairs — leg health check + parametric rebuild
  swivel_seat  office chairs — symmetry only here; graft_chair_base.py owns the base
  boxy         cabinets/shelves/wardrobes — plinth rebuild, mild smooth (keep edges)
  upholstered  sofas/couches/armchairs/beds — strong volume-preserving smooth, plinth
  panel        mirrors/frames/monitors/TVs/clocks — flatten the blobby back to a slab
  slender      lamps/planters — protect thin verticals, no symmetry forcing
  prop         everything else — safe universal clean only

Universal stages (each archetype toggles/tunes them):
  1. debris filter        up-aware: keeps support-like thin pieces under the body
  2. watertight repair    pymeshfix per connected component (never collapses parts)
  3. symmetry snap        DETECTS the bilateral plane (axis+offset scored by chamfer),
                          then soft-blends drift out or mirror-merges the richer half.
                          Fixes the historic mirror brittleness: no X=0 assumption.
  4. Taubin smooth        volume-preserving, per-archetype iterations
  5. decimation           per-archetype face budget (raw TripoSR is 70k-200k faces)
  6. panel flatten        soft-clamp thickness along the thin axis (tanh, no shear walls)
  7. support rebuild      bottom-band health check; only if broken: cut + parametric
                          legs4 / pedestal / plinth sized from the body footprint
  8. contact flatten      snap near-floor vertices flush so items sit flat

Native frame: TripoSR exports are X-up (verified empirically on chair/desk/table
outputs; the viewer's fixed [180,0,90] rotation assumes it). Override via env.

Env knobs:
  SCS_REPAIR_PACKS=0          kill-switch (pipeline falls back to old behaviour)
  SCS_REPAIR_ARCHETYPE=<name> force an archetype (the office-chair UI toggle uses this)
  SCS_REPAIR_UP_AXIS=0        native up axis (default 0 = X)

CLI (repair an existing GLB, JSON report on the last line):
  python repair_packs.py <in.glb> <out.glb> [--label "office chair"] [--category Table]
"""
from __future__ import annotations
import os, sys, json, argparse
import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_and_optimize import _capture_color, _apply_color

UP = int(os.environ.get("SCS_REPAIR_UP_AXIS", "0"))

# label/category slug -> repair archetype. Labels win over categories (finer).
_LABEL_ARCHETYPE = {
    "office_chair": "swivel_seat", "swivel_chair": "swivel_seat", "desk_chair": "swivel_seat",
    "chair": "legged", "stool": "legged", "bench": "legged",
    "table": "legged", "desk": "legged", "dining_table": "legged",
    "conference_table": "legged", "coffee_table": "legged", "side_table": "legged",
    "armchair": "upholstered", "sofa": "upholstered", "couch": "upholstered", "bed": "upholstered",
    "cabinet": "boxy", "wardrobe": "boxy", "dresser": "boxy", "filing_cabinet": "boxy",
    "storage_cabinet": "boxy", "bookshelf": "boxy", "shelf": "boxy",
    "mirror": "panel", "picture_frame": "panel", "clock": "panel", "tv": "panel",
    "monitor": "panel", "computer": "panel", "window": "panel", "door": "panel",
    "lamp": "slender", "light": "slender", "floor_lamp": "slender",
    "planter": "slender", "plant": "slender",
}
_CATEGORY_ARCHETYPE = {
    "chair": "legged", "table": "legged", "sofa": "upholstered", "bed": "upholstered",
    "cabinet": "boxy", "shelf": "boxy", "lighting": "slender",
}

# knob defaults per archetype: symmetry mode, support type, smooth iters, face budget
PACKS = {
    "legged":      dict(symmetry="strict", support="auto",  smooth=8,  faces=15000, panel=False),
    "swivel_seat": dict(symmetry="soft",   support="off",   smooth=0,  faces=45000, panel=False),
    "boxy":        dict(symmetry="soft",   support="plinth", smooth=5,  faces=15000, panel=False),
    "upholstered": dict(symmetry="soft",   support="plinth", smooth=14, faces=15000, panel=False),
    "panel":       dict(symmetry="soft",   support="off",   smooth=4,  faces=10000, panel=True),
    "slender":     dict(symmetry="off",    support="off",   smooth=6,  faces=12000, panel=False),
    "prop":        dict(symmetry="off",    support="off",   smooth=8,  faces=15000, panel=False),
}


def _norm(s):
    return (s or "").strip().lower().replace(" ", "_")


def resolve_archetype(label=None, category=None):
    forced = _norm(os.environ.get("SCS_REPAIR_ARCHETYPE", ""))
    if forced in PACKS:
        return forced
    lab = _norm(label)
    if "office" in lab or "swivel" in lab:          # mirrors triposr.js shouldGraftChair
        return "swivel_seat"
    if lab in _LABEL_ARCHETYPE:
        return _LABEL_ARCHETYPE[lab]
    cat = _norm(category)
    if cat in _CATEGORY_ARCHETYPE:
        return _CATEGORY_ARCHETYPE[cat]
    return "prop"


def _lat_axes():
    return [i for i in range(3) if i != UP]


# ── stage 1: up-aware debris filter (keeps support-like thin parts) ──────────
def _debris_filter(mesh, report):
    comps = mesh.split(only_watertight=False)
    if len(comps) <= 1:
        return mesh
    total = sum(len(c.faces) for c in comps)
    main = max(comps, key=lambda c: len(c.faces))
    mb = main.bounds
    a, b = _lat_axes()
    kept, dropped = [], 0
    for c in comps:
        ratio = len(c.faces) / total
        if ratio >= 0.10:
            kept.append(c); continue
        e = c.bounding_box.extents
        cent = c.bounding_box.centroid
        inside = (mb[0][a] <= cent[a] <= mb[1][a]) and (mb[0][b] <= cent[b] <= mb[1][b])
        support_like = e[UP] >= 1.8 * max(e[a], 1e-6) and e[UP] >= 1.8 * max(e[b], 1e-6)
        if support_like and inside and ratio >= 0.003:
            kept.append(c); continue                 # a leg / column / pole
        if inside and ratio >= 0.006:
            kept.append(c); continue                 # attached chunk of the body
        dropped += 1
    report["debris_dropped"] = dropped
    return trimesh.util.concatenate(kept) if kept else main


# ── stage 2: watertight repair, per component (parts survive) ────────────────
def _watertight(mesh, report):
    import pymeshfix
    def fix(part):
        vc, fc = pymeshfix.clean_from_arrays(
            np.asarray(part.vertices, np.float64), np.asarray(part.faces, np.int32),
            joincomp=True, remove_smallest_components=False)
        return trimesh.Trimesh(vertices=vc, faces=fc, process=True) if len(vc) and len(fc) else part
    parts = mesh.split(only_watertight=False)
    out = trimesh.util.concatenate([fix(p) for p in parts]) if len(parts) > 1 else fix(mesh)
    report["watertight"] = f"pymeshfix x{max(len(parts), 1)}"
    return out


# ── stage 3: symmetry — detect the bilateral plane, then snap to it ──────────
def _detect_symmetry(mesh, samples=3000):
    """Best (axis, plane_offset, score) among the two lateral axes. Score is the
    mean chamfer distance between the surface and its own reflection, / diagonal."""
    from scipy.spatial import cKDTree
    pts = mesh.sample(samples)
    diag = float(np.linalg.norm(mesh.extents))
    tree = cKDTree(pts)
    best = (None, 0.0, np.inf)
    for ax in _lat_axes():
        c0 = float(pts[:, ax].mean())
        for c in np.linspace(c0 - 0.02 * diag, c0 + 0.02 * diag, 5):
            ref = pts.copy(); ref[:, ax] = 2 * c - ref[:, ax]
            d, _ = tree.query(ref, k=1)
            score = float(d.mean()) / diag
            if score < best[2]:
                best = (ax, c, score)
    return best


def _reflect_matrix(ax, c):
    M = np.eye(4); M[ax, ax] = -1.0; M[ax, 3] = 2.0 * c
    return M


def _symmetrize(mesh, mode, report):
    """soft: blend each vertex toward what the OTHER side says it should be.
    strict + medium asymmetry: mirror the richer half about the detected plane."""
    from scipy.spatial import cKDTree
    ax, c, score = _detect_symmetry(mesh)
    report["symmetry"] = {"axis": int(ax), "offset": round(c, 4), "score": round(score, 5)}
    diag = float(np.linalg.norm(mesh.extents))
    if score > 0.030:                               # genuinely asymmetric — leave it
        report["symmetry"]["applied"] = "none (asymmetric)"
        return mesh
    if mode == "strict" and score > 0.010:
        # one side is damaged: rebuild from the richer half
        side = mesh.triangles_center[:, ax] >= c
        keep = side if side.sum() >= (~side).sum() else ~side
        half = mesh.submesh([np.where(keep)[0]], append=True)
        mirror = half.copy()
        mirror.apply_transform(_reflect_matrix(ax, c))
        mirror.invert()
        out = trimesh.util.concatenate([half, mirror])
        out.merge_vertices(digits_vertex=4)
        report["symmetry"]["applied"] = "mirror-merge"
        return out
    # soft blend: v -> midpoint of v and the reflection of its cross-plane match
    pts = mesh.sample(4000)
    tree = cKDTree(pts)
    v = mesh.vertices.copy()
    refl = v.copy(); refl[:, ax] = 2 * c - refl[:, ax]
    d, idx = tree.query(refl, k=1)
    cap = 0.02 * diag
    ok = d < cap
    target = pts[idx]; target[:, ax] = 2 * c - target[:, ax]   # reflect match back to v's side
    v[ok] = 0.5 * v[ok] + 0.5 * target[ok]
    mesh.vertices = v
    report["symmetry"]["applied"] = f"soft-blend ({int(ok.sum())}/{len(v)} verts)"
    return mesh


# ── stage 6: panel flatten (mirrors/frames/monitors get blobby backs) ─────────
def _panel_flatten(mesh, report):
    a, b = _lat_axes()
    e = mesh.extents
    thin = min((UP, a, b), key=lambda i: e[i])
    if thin == UP:                                  # standing panel is thin laterally
        thin = a if e[a] < e[b] else b
    v = mesh.vertices.copy()
    m = float(np.median(v[:, thin]))
    t = max(0.06 * e[UP], 0.04 * max(e[a], e[b]))   # half-thickness allowance
    v[:, thin] = m + t * np.tanh((v[:, thin] - m) / t)
    mesh.vertices = v
    report["panel_flatten"] = {"axis": int(thin), "half_thickness": round(t, 4)}
    return mesh


# ── stage 7: support rebuild — health check, then parametric legs/pedestal/plinth
def _support_health(mesh):
    """Is the bottom structurally sound? Returns (healthy, diagnostics)."""
    bnd = mesh.bounds
    floor, H = bnd[0][UP], bnd[1][UP] - bnd[0][UP]
    comps = mesh.split(only_watertight=False)
    total = sum(len(c.faces) for c in comps) or 1
    bottom = [c for c in comps if c.bounds[1][UP] < floor + 0.35 * H]
    biggest = max((len(c.faces) / total for c in bottom), default=0.0)
    contact = mesh.vertices[mesh.vertices[:, UP] < floor + 0.02 * H]
    a, b = _lat_axes()
    e = mesh.extents
    if len(contact) >= 8:
        spread_a = np.ptp(contact[:, a]) / max(e[a], 1e-6)
        spread_b = np.ptp(contact[:, b]) / max(e[b], 1e-6)
    else:
        spread_a = spread_b = 0.0
    diag = {"bottom_comps": len(bottom), "biggest_bottom_frac": round(biggest, 4),
            "contact_verts": int(len(contact)),
            "contact_spread": [round(spread_a, 3), round(spread_b, 3)]}
    broken = (len(bottom) > 4) or (len(contact) < 8) or \
             (len(bottom) > 0 and biggest < 0.015) or (max(spread_a, spread_b) < 0.25)
    return (not broken), diag


def _rot_Z_to_up():
    if UP == 0:
        return trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    if UP == 1:
        return trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    return np.eye(4)


# ── v2 evidence gathering: what support did the generator TRY to build? ───────
def _cluster_2d(points, radius):
    """Union-find clustering of 2D points within `radius`. Returns cluster centres."""
    from scipy.spatial import cKDTree
    if not len(points):
        return []
    tree = cKDTree(points)
    parent = list(range(len(points)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, j in tree.query_pairs(radius):
        parent[find(i)] = find(j)
    groups = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(points[i])
    return [np.mean(g, axis=0) for g in groups.values()]


def _footprint_is_round(band_pts_2d):
    """True if the cross-section reads as a circle: hull area vs bounding-circle
    area (a square top also has bbox aspect 1.0 — this test tells them apart)."""
    try:
        from scipy.spatial import ConvexHull
        if len(band_pts_2d) < 12:
            return False
        hull = ConvexHull(band_pts_2d)
        centre = band_pts_2d.mean(axis=0)
        r = float(np.linalg.norm(band_pts_2d - centre, axis=1).max())
        return hull.volume / (np.pi * r * r + 1e-9) > 0.80   # hull.volume == area in 2D
    except Exception:
        return False


def _infer_support_topology(mesh, report):
    """Cluster the bottom-band leg STUBS the generator actually produced — they sit
    in roughly the right places even when broken. Returns (kind, positions) where
    positions are lateral (a, b) leg centres, or (kind, None) for pedestal/plinth."""
    a, b = _lat_axes()
    bnd = mesh.bounds
    floor, H = bnd[0][UP], bnd[1][UP] - bnd[0][UP]
    e = mesh.extents
    span = max(e[a], e[b])
    comps = mesh.split(only_watertight=False)
    total = sum(len(c.faces) for c in comps) or 1
    # stubs: components living in the bottom 35% that aren't the main body
    stubs = [c for c in comps
             if c.bounds[1][UP] < floor + 0.40 * H and len(c.faces) / total < 0.5]
    centres = np.array([[c.bounding_box.centroid[a], c.bounding_box.centroid[b]] for c in stubs]) \
        if stubs else np.empty((0, 2))
    clusters = _cluster_2d(centres, radius=0.16 * span)
    n = len(clusters)
    body_centre = np.array([(bnd[0][a] + bnd[1][a]) / 2, (bnd[0][b] + bnd[1][b]) / 2])
    band = mesh.vertices[mesh.vertices[:, UP] < floor + 0.30 * H]
    round_top = _footprint_is_round(band[:, [a, b]]) if len(band) else False
    report["support_evidence"] = {"stub_components": len(stubs), "stub_clusters": n,
                                  "round_footprint": bool(round_top)}
    if n == 1 and np.linalg.norm(clusters[0] - body_centre) < 0.18 * span:
        return "pedestal", None                       # one central stub = column base
    if n == 2:
        return "trestle", clusters                    # two end supports
    if n == 3:
        return "tripod", clusters
    if 4 <= n <= 5:
        return "legsN", clusters                      # legs where the stubs were
    if round_top:
        return "pedestal", None                       # no usable stubs, round top
    return "legs4", None                              # default: 4 corner legs


def _world_box(w_a, w_b, h_up, at_a, at_b, base_up):
    """Axis-aligned box built DIRECTLY in world axes (a, b lateral, UP vertical)."""
    a, b = _lat_axes()
    ext = np.zeros(3); ext[a], ext[b], ext[UP] = w_a, w_b, h_up
    box = trimesh.creation.box(extents=ext)
    tr = np.zeros(3); tr[a], tr[b], tr[UP] = at_a, at_b, base_up + h_up / 2
    box.apply_translation(tr)
    return box


def _world_cylinder(radius, h_up, at_a, at_b, base_up, sections=20):
    """Vertical cylinder built in world coords (axis along UP)."""
    a, b = _lat_axes()
    cyl = trimesh.creation.cylinder(radius=radius, height=h_up, sections=sections)
    cyl.apply_transform(_rot_Z_to_up())              # cylinder axis Z -> UP (origin-centred)
    tr = np.zeros(3); tr[a], tr[b], tr[UP] = at_a, at_b, base_up + h_up / 2
    cyl.apply_translation(tr)
    return cyl


def _build_supports(kind, foot_lo, foot_hi, floor, cut, H, positions=None):
    """Parametric supports built directly in WORLD coordinates (no local-frame
    rotation — that swapped the plan axes and put evidence-based legs in the
    wrong place). foot_* are (a, b) lateral bounds; positions are (a, b) centres."""
    w = foot_hi[0] - foot_lo[0]
    d = foot_hi[1] - foot_lo[1]
    cx, cy = (foot_lo[0] + foot_hi[0]) / 2, (foot_lo[1] + foot_hi[1]) / 2
    height = (cut - floor) + 0.06 * H               # overlap into the kept body
    parts = []
    if kind == "pedestal":
        parts.append(_world_cylinder(0.07 * max(w, d), height, cx, cy, floor, sections=24))
        parts.append(_world_cylinder(0.30 * max(w, d), 0.06 * height + 1e-4, cx, cy, floor, sections=32))
    elif kind == "plinth":
        parts.append(_world_box(w * 0.94, d * 0.94, height, cx, cy, floor))
    elif kind == "trestle" and positions is not None and len(positions):
        slab_t = max(0.05 * max(w, d), 0.02)
        for p in positions:
            pa = float(np.clip(p[0], foot_lo[0] + slab_t / 2, foot_hi[0] - slab_t / 2))
            parts.append(_world_box(slab_t, d * 0.86, height, pa, cy, floor))
    elif kind in ("tripod", "legsN") and positions is not None and len(positions):
        r_leg = max(0.035 * max(w, d), 0.014)
        for p in positions:
            pa = float(np.clip(p[0], foot_lo[0] + r_leg, foot_hi[0] - r_leg))
            pb = float(np.clip(p[1], foot_lo[1] + r_leg, foot_hi[1] - r_leg))
            parts.append(_world_cylinder(r_leg, height, pa, pb, floor, sections=16))
    if not parts:                                    # legs4 default: corners of the footprint
        leg_t = max(0.045 * max(w, d), 0.02)
        ins_a, ins_b = 0.10 * w + leg_t / 2, 0.10 * d + leg_t / 2
        for sa in (-1, 1):
            for sb in (-1, 1):
                parts.append(_world_box(leg_t, leg_t, height,
                                        cx + sa * (w / 2 - ins_a), cy + sb * (d / 2 - ins_b), floor))
    return trimesh.util.concatenate(parts)


def _rebuild_supports(mesh, support, report):
    healthy, diag = _support_health(mesh)
    report["support_health"] = diag
    if healthy:
        report["support"] = "healthy (kept original)"
        return mesh
    # v2: read the evidence BEFORE cutting — the broken stubs carry the layout
    positions = None
    if support == "auto":
        kind, positions = _infer_support_topology(mesh, report)
    else:
        kind = support
    bnd = mesh.bounds
    floor, H = bnd[0][UP], bnd[1][UP] - bnd[0][UP]
    cut = floor + 0.20 * H
    tc = mesh.triangles_center
    keep = np.where(tc[:, UP] >= cut)[0]
    if not len(keep):
        report["support"] = "skipped (cut would remove everything)"
        return mesh
    body = mesh.submesh([keep], append=True)
    # the cut opens the body — close it so the exported IFC stays watertight
    try:
        trimesh.repair.fill_holes(body)
        if not body.is_watertight:
            import pymeshfix
            vc, fc = pymeshfix.clean_from_arrays(
                np.asarray(body.vertices, np.float64), np.asarray(body.faces, np.int32),
                joincomp=True, remove_smallest_components=False)
            if len(vc) and len(fc) and len(fc) >= 0.3 * len(body.faces):
                body = trimesh.Trimesh(vertices=vc, faces=fc, process=True)
    except Exception:
        pass
    # footprint = the body cross-section just above the cut (what the supports must carry)
    band = body.vertices[body.vertices[:, UP] < cut + 0.08 * H]
    if len(band) < 8:
        band = body.vertices
    a, b = _lat_axes()
    foot_lo = (float(band[:, a].min()), float(band[:, b].min()))
    foot_hi = (float(band[:, a].max()), float(band[:, b].max()))
    if kind == "legs4" and positions is None:
        # place legs under REAL material: the farthest band point from centre in
        # each footprint quadrant (bbox corners can be empty air — e.g. a shell
        # tabletop that doesn't span its own bounding box). If the bottom material
        # is only a thin sliver (hull barely covers the footprint), legs would
        # float — a solid plinth is the safe rebuild there.
        cx, cy = (foot_lo[0] + foot_hi[0]) / 2, (foot_lo[1] + foot_hi[1]) / 2
        pts = band[:, [a, b]]
        w_f, d_f = max(foot_hi[0] - foot_lo[0], 1e-6), max(foot_hi[1] - foot_lo[1], 1e-6)
        cover = 0.0
        try:
            from scipy.spatial import ConvexHull
            if len(pts) >= 8:
                cover = ConvexHull(pts).volume / (w_f * d_f)   # 2D hull.volume == area
        except Exception:
            pass
        quads = {}
        for p in pts:
            q = (p[0] >= cx, p[1] >= cy)
            d = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
            if q not in quads or d > quads[q][0]:
                quads[q] = (d, p)
        if cover >= 0.22 and len(quads) >= 3:
            centre = np.array([cx, cy])
            positions = [centre + (np.asarray(v[1]) - centre) * 0.97 for v in quads.values()]
            kind = "legsN"
        else:
            kind = "plinth"
        report["support_evidence"] = {**report.get("support_evidence", {}),
                                      "bottom_cover": round(cover, 3), "quadrants": len(quads)}
    sup = _build_supports(kind, foot_lo, foot_hi, floor, cut, H, positions)
    out = trimesh.util.concatenate([body, sup])
    n_pos = len(positions) if positions is not None else 0
    report["support"] = f"rebuilt: {kind}" + (f" at {n_pos} detected stub positions" if n_pos else "")
    return out


# ── stage 8: contact flatten ──────────────────────────────────────────────────
def _contact_flatten(mesh, report):
    bnd = mesh.bounds
    floor, H = bnd[0][UP], bnd[1][UP] - bnd[0][UP]
    v = mesh.vertices.copy()
    near = v[:, UP] < floor + 0.015 * H
    if near.sum():
        v[near, UP] = floor
        mesh.vertices = v
        report["contact_flatten"] = int(near.sum())
    return mesh


# ── the dispatcher ────────────────────────────────────────────────────────────
def repair_mesh(mesh, label=None, category=None, archetype=None):
    """Universal archetype-driven repair. Returns (mesh, report). Never raises:
    each stage falls back to the pre-stage mesh on error."""
    name = archetype or resolve_archetype(label, category)
    pack = PACKS[name]
    report = {"archetype": name, "label": label or "", "faces_in": int(len(mesh.faces))}
    color = _capture_color(mesh)

    def stage(fn, *args):
        nonlocal mesh
        try:
            mesh = fn(mesh, *args)
        except Exception as e:
            report[f"{fn.__name__}_error"] = str(e)

    stage(_debris_filter, report)
    stage(_watertight, report)
    if pack["symmetry"] != "off":
        stage(_symmetrize, pack["symmetry"], report)
    if pack["smooth"] > 0:
        try:
            trimesh.smoothing.filter_taubin(mesh, iterations=pack["smooth"])
            report["smooth"] = f"taubin x{pack['smooth']}"
        except Exception as e:
            report["smooth_error"] = str(e)
    if pack["faces"] and len(mesh.faces) > pack["faces"]:
        try:
            import fast_simplification
            vs, fs = fast_simplification.simplify(
                np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int32),
                target_reduction=1.0 - pack["faces"] / len(mesh.faces))
            mesh = trimesh.Trimesh(vertices=vs, faces=fs, process=True)
            report["decimated_to"] = int(len(mesh.faces))
        except Exception as e:
            report["decimate_error"] = str(e)
    if pack["panel"]:
        stage(_panel_flatten, report)
    # sweep + heal BEFORE the support rebuild: the sweep must never see the
    # parametric supports (a 12-face plinth box reads as a crumb), and the health
    # check judges a cleaner mesh. The rebuild heals its own cut.
    stage(_finalize, report)
    if pack["support"] != "off":
        stage(_rebuild_supports, pack["support"], report)
    stage(_contact_flatten, report)
    _apply_color(mesh, color)
    report["faces_out"] = int(len(mesh.faces))
    return mesh, report


def _finalize(mesh, report):
    """Last pass: sweep leftover crumbs (decimation fragments, noise) and make
    every surviving component watertight — the support cut and quadric decimation
    both open geometry, and the exported IFC wants closed solids."""
    parts = mesh.split(only_watertight=False)
    total = sum(len(p.faces) for p in parts) or 1
    kept = [p for p in parts if len(p.faces) / total >= 0.003]
    if not kept:
        kept = [max(parts, key=lambda p: len(p.faces))]
    healed = 0
    out = []
    for p in kept:
        if not p.is_watertight:
            try:
                trimesh.repair.fill_holes(p)
                if not p.is_watertight:
                    import pymeshfix
                    vc, fc = pymeshfix.clean_from_arrays(
                        np.asarray(p.vertices, np.float64), np.asarray(p.faces, np.int32),
                        joincomp=True, remove_smallest_components=False)
                    if len(vc) and len(fc):
                        p2 = trimesh.Trimesh(vertices=vc, faces=fc, process=True)
                        if len(p2.faces) >= 0.3 * len(p.faces):   # don't accept a collapse
                            p = p2
                healed += 1
            except Exception:
                pass
        out.append(p)
    report["finalize"] = {"crumbs_dropped": len(parts) - len(kept), "healed": healed,
                          "parts": len(out)}
    return trimesh.util.concatenate(out) if len(out) > 1 else out[0]


def repair_file(inp, outp, label=None, category=None):
    mesh = trimesh.load(inp, force="mesh")
    mesh, report = repair_mesh(mesh, label=label, category=category)
    mesh.export(outp)
    report["ok"] = True
    report["kb"] = os.path.getsize(outp) // 1024
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--label", default=None)
    ap.add_argument("--category", default=None)
    args = ap.parse_args()
    print(json.dumps(repair_file(args.inp, args.out, args.label, args.category)))
