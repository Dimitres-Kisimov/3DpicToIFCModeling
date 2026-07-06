"""graft_chair_base.py — replace an office chair's broken TripoSR base with a clean 5-star wheelbase.

Keeps the generated seat/back/arms, removes the bottom (broken) base region, and grafts a clean
parametric 5-star base + gas column + casters, sized to the chair. Colour preserved.

    python graft_chair_base.py <chair.glb> <out.glb>
"""
import sys, os
import numpy as np
import trimesh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_and_optimize import _capture_color, _apply_color, _voxel_solidify, clean_mesh


def _rot_Z_to(axis):
    """Rotation that maps local +Z onto world axis (0=X,1=Y,2=Z)."""
    if axis == 0:
        return trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    if axis == 1:
        return trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    return np.eye(4)


def _level_seat(m, up):
    """TripoSR often generates the chair reclined. Rotate so the seat plane is horizontal
    (its normal aligns with the up-axis) — otherwise the level base clashes with a tilted seat."""
    def fit(mesh):
        """(tilt_deg, plane_normal) of the flat seat-top surface, or None if not found."""
        b = mesh.bounds; H = b[1][up] - b[0][up]
        tc = mesh.triangles_center; nrm = mesh.face_normals
        band = (tc[:, up] > b[0][up] + 0.33 * H) & (tc[:, up] < b[0][up] + 0.62 * H)
        flat = band & (np.abs(nrm[:, up]) > 0.75)      # the flat SITTING surface, not cushion sides
        if flat.sum() < 15:
            flat = band & (np.abs(nrm[:, up]) > 0.55)  # relax if the pan is very rounded
        if flat.sum() < 15:
            return None
        pts = tc[flat]; c = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - c)              # least-squares plane fit on seat-top centres
        n = vt[2]; n = n if n[up] >= 0 else -n
        return np.degrees(np.arccos(min(1.0, abs(n[up])))), n

    # Iterate, but ONLY keep a rotation that actually reduces the measured tilt. A clean exec-chair
    # seat converges to ~0; a recliner/footrest with no single flat seat plane is left alone rather
    # than spun worse.
    total = 0.0
    for _ in range(6):
        cur = fit(m)
        if cur is None:
            break
        tilt, n = cur
        if tilt < 1.0:
            break
        target = np.zeros(3); target[up] = 1.0
        m2 = m.copy(); m2.apply_transform(trimesh.geometry.align_vectors(n, target))
        if int(np.argmax(m2.extents)) != up:           # would flip a near-cubic chair sideways
            break
        nxt = fit(m2)
        if nxt is None or nxt[0] > tilt - 0.5:         # no real improvement — stop, keep current
            break
        m = m2; total += tilt - nxt[0]
    if total > 0.5:
        print("leveled seat: reduced recline by %.1f deg" % total)
    return m


def build(inp, outp, do_clean=True):
    m = trimesh.load(inp, force="mesh")
    color = _capture_color(m)
    # "the mesh thing" — decimate + smooth + debris-remove the generated chair BEFORE we graft,
    # so the clean base we add afterwards is never touched by the debris filter.
    if do_clean:
        try:
            m, _ = clean_mesh(m, target_faces=15000, solidify=False, ground=False)
        except Exception as ex:
            print("clean skipped:", ex)
    # NOTE: seat-leveling + orientation-canonicalize were removed — they reoriented the mesh and,
    # combined with the app viewer's fixed rotation, threw chairs sideways. The graft now keeps the
    # mesh in TripoSR's native frame, which the viewer already displays upright.
    e = m.extents
    up = int(np.argmax(e))                      # tallest axis = the chair's vertical
    b = m.bounds
    floor, ceil = b[0][up], b[1][up]
    H = ceil - floor
    oth = [i for i in range(3) if i != up]
    cA = (b[0][oth[0]] + b[1][oth[0]]) / 2
    cB = (b[0][oth[1]] + b[1][oth[1]]) / 2
    foot = max(e[oth[0]], e[oth[1]])
    cut = floor + 0.20 * H                        # remove the bottom 20% (the broken base)

    # 1) keep the chair ABOVE the cut (seat/back/arms/upper pedestal)
    tc = m.triangles_center
    keep = np.where(tc[:, up] >= cut)[0]
    top = m.submesh([keep], append=True) if len(keep) else m
    # strong (volume-preserving) smoothing to take TripoSR's rugged faceting off the seat & back.
    # Taubin's lambda/mu keeps volume, so even a high pass count softens noise without melting shape.
    try:
        trimesh.smoothing.filter_taubin(top, iterations=int(os.environ.get("SCS_CHAIR_SMOOTH", "16")))
    except Exception as ex:
        print("top smooth skipped:", ex)

    # 2) build a clean 5-star base in local Z-up (wheels at z=0, hub above)
    r = foot * float(os.environ.get("SCS_BASE_RADIUS_FRAC", "0.42"))   # spoke length; keep within the seat
    hub_h, wr = r * 0.16, r * 0.13
    parts = [trimesh.creation.cylinder(radius=r * 0.17, height=hub_h)]      # hub
    col_h = (cut - floor) + 0.12 * H                                        # gas column past the cut
    col = trimesh.creation.cylinder(radius=r * 0.09, height=col_h)
    col.apply_translation([0, 0, col_h / 2 + hub_h * 0.3]); parts.append(col)
    for k in range(5):                            # 5 spokes + casters at 72 deg
        ang = k * 2 * np.pi / 5
        Rz = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
        spoke = trimesh.creation.box(extents=[r, r * 0.12, hub_h * 0.55])
        spoke.apply_translation([r / 2, 0, -hub_h * 0.05]); spoke.apply_transform(Rz); parts.append(spoke)
        wheel = trimesh.creation.cylinder(radius=wr, height=wr * 0.8)
        wheel.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        wheel.apply_transform(Rz)
        wheel.apply_translation([r * np.cos(ang), r * np.sin(ang), -hub_h * 0.35]); parts.append(wheel)
    base = trimesh.util.concatenate(parts)
    # fuse hub+column+spokes+casters into ONE watertight solid so the debris filter and the IFC
    # optimizer keep it as a single component (individual casters would otherwise be dropped).
    try:
        tb = base.bounds.copy()                         # remember the true world-space size
        base = _voxel_solidify(base, pitch_frac=0.010)
        # trimesh's VoxelGrid.marching_cubes returns voxel-INDEX coords (scaled by 1/pitch) —
        # refit the solid back onto the original AABB so it isn't ~100x too big.
        sb = base.bounds
        ssize = sb[1] - sb[0]; ssize[ssize == 0] = 1e-9
        base.apply_translation(-sb[0])
        base.apply_scale((tb[1] - tb[0]) / ssize)
        base.apply_translation(tb[0])
        if len(base.faces) > 3500:                      # voxel remesh is dense — slim it down
            import fast_simplification
            red = 1.0 - 3500 / len(base.faces)
            vs, fs = fast_simplification.simplify(
                np.asarray(base.vertices, np.float32), np.asarray(base.faces, np.int32),
                target_reduction=float(red))
            base = trimesh.Trimesh(vertices=vs, faces=fs, process=True)
        trimesh.smoothing.filter_taubin(base, iterations=6)   # take the voxel edge off
    except Exception as ex:
        print("base solidify skipped:", ex)
    base.apply_translation([0, 0, -base.bounds[0][2]])     # wheels to z=0
    base.apply_transform(_rot_Z_to(up))                    # Z-up -> chair's up-axis

    # 3) position: base floor at the chair floor, footprint centred under the seat
    bb = base.bounds
    tr = np.zeros(3)
    tr[up] = floor - bb[0][up]
    tr[oth[0]] = cA - (bb[0][oth[0]] + bb[1][oth[0]]) / 2
    tr[oth[1]] = cB - (bb[0][oth[1]] + bb[1][oth[1]]) / 2
    base.apply_translation(tr)

    out = trimesh.util.concatenate([top, base])
    _apply_color(out, color)
    out.export(outp)
    print("grafted: kept %d chair faces + clean 5-star base (%d faces) -> %s"
          % (len(top.faces), len(base.faces), outp))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
