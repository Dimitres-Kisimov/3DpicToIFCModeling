"""
TripoSR mesh post-processing — fixes the documented single-view failure modes
that surface on chair photographs (asymmetric / discontinuous legs, floating
debris around the seat).

Pipeline:
  1. Component filter — *relaxed*. Keeps small components if they are vertical
     and thin (i.e. probably a chair / table / lamp leg), otherwise drops
     true debris. This is the most common reason TripoSR chairs ship without
     legs: the legs ARE generated but get filtered as "spikes".
  2. Centroid translation to origin.
  3. Orientation fix (TripoSR sometimes outputs upside-down).
  4. *Mirror symmetry* across the X = 0 plane. Picks the side of the mesh with
     more triangles (visually richer), mirrors it onto the other side. Removes
     per-leg left/right drift while keeping the silhouette correct.
  5. Vertex merge — closes hairline gaps that the symmetry step can introduce.
  6. Humphrey smoothing (preserves volume better than Laplacian).

All steps are bounded: a step that errors does not corrupt the mesh; the
mesh-before-that-step is returned instead. The helper never raises.

Tunable via env vars for production sites that want different behaviour:
  SCS_TRIPOSR_KEEP_VERTICAL_RATIO   default 2.0 (vertical extent must be
                                    this many times either lateral extent
                                    for a "vertical thin" component to be
                                    kept regardless of face-count)
  SCS_TRIPOSR_MIRROR                default '1' (set '0' to disable)
  SCS_TRIPOSR_SMOOTH_ITER           default 5

Licence: MIT (matches TripoSR).
"""
from __future__ import annotations

import os
import numpy as np
import trimesh


def _safe(stage_name: str, fn, mesh):
    """Run fn(mesh) but return original mesh on any failure. Logs if it falls
    back so we can see what stage misbehaved on a given input."""
    try:
        out = fn(mesh)
        if out is None:
            return mesh
        return out
    except Exception as e:
        print(f"[triposr-postproc] {stage_name} skipped: {e}", flush=True)
        return mesh


# ---------------------------------------------------------------------------
# Stage 1 — Relaxed component filter that keeps vertical thin pieces (legs)
# ---------------------------------------------------------------------------
def _filter_components_keep_legs(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    components = mesh.split(only_watertight=False)
    if not components:
        return mesh
    total_faces = sum(len(c.faces) for c in components)
    if total_faces == 0:
        return mesh

    keep_vert_ratio = float(os.environ.get("SCS_TRIPOSR_KEEP_VERTICAL_RATIO", "2.0"))
    kept = []
    dropped_summary = {"true_debris": 0, "horizontal_spike": 0, "ok_main": 0, "ok_leg": 0}

    for c in components:
        face_ratio = len(c.faces) / total_faces
        ext = c.bounding_box.extents
        if ext.max() <= 0:
            continue

        # Detect vertical-thin shape: Z-extent is dominant.
        ext_x, ext_y, ext_z = float(ext[0]), float(ext[1]), float(ext[2])
        is_vertical_thin = (
            ext_z >= keep_vert_ratio * max(ext_x, 1e-6)
            and ext_z >= keep_vert_ratio * max(ext_y, 1e-6)
        )

        if face_ratio >= 0.10:
            kept.append(c); dropped_summary["ok_main"] += 1
            continue
        if is_vertical_thin and face_ratio >= 0.0005:
            kept.append(c); dropped_summary["ok_leg"] += 1
            continue
        if face_ratio < 0.002:
            dropped_summary["true_debris"] += 1
            continue
        compactness = ext.min() / ext.max()
        if compactness < 0.02 and face_ratio < 0.05:
            dropped_summary["horizontal_spike"] += 1
            continue
        # Default: keep it (less aggressive than the original filter)
        kept.append(c)

    if not kept:
        return mesh
    joined = trimesh.util.concatenate(kept) if len(kept) > 1 else kept[0]
    print(
        f"[triposr-postproc] components: kept {len(kept)}/{len(components)} "
        f"(main={dropped_summary['ok_main']}, leg-like={dropped_summary['ok_leg']}, "
        f"dropped debris={dropped_summary['true_debris']}, "
        f"horizontal-spike={dropped_summary['horizontal_spike']})",
        flush=True,
    )
    return joined


# ---------------------------------------------------------------------------
# Stage 2 — Centre at origin
# ---------------------------------------------------------------------------
def _center(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh.apply_translation(-mesh.bounding_box.centroid)
    return mesh


# ---------------------------------------------------------------------------
# Stage 3 — Orientation fix (TripoSR sometimes generates upside-down)
# ---------------------------------------------------------------------------
def _orient_upright(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    centroid_y = mesh.vertices[:, 1].mean()
    if centroid_y > 0.05:
        R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
        mesh.apply_transform(R)
        print("[triposr-postproc] applied orientation correction (flipped)", flush=True)
    return mesh


# ---------------------------------------------------------------------------
# Stage 4 — Mirror symmetry across X = 0 plane
# ---------------------------------------------------------------------------
def _mirror_symmetry_x(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Pick the side of the mesh with more triangles, mirror it onto the
    other side. Removes per-leg left/right drift while preserving the
    silhouette characteristic of the input photograph."""
    if not bool(int(os.environ.get("SCS_TRIPOSR_MIRROR", "1"))):
        return mesh

    faces = mesh.faces
    if len(faces) == 0:
        return mesh

    # Centroid of each face — used to decide which side a face belongs to.
    face_centroids = mesh.vertices[faces].mean(axis=1)
    left_mask = face_centroids[:, 0] < 0
    right_mask = ~left_mask

    n_left = int(left_mask.sum())
    n_right = int(right_mask.sum())
    if n_left == 0 or n_right == 0:
        # All on one side — nothing meaningful to mirror against
        return mesh

    keep_left = n_left >= n_right
    keep_faces = faces[left_mask] if keep_left else faces[right_mask]
    print(
        f"[triposr-postproc] mirror: kept "
        f"{'LEFT' if keep_left else 'RIGHT'} side "
        f"({len(keep_faces)} of {len(faces)} faces)",
        flush=True,
    )

    half = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                            faces=keep_faces.copy(),
                            process=False)
    half.remove_unreferenced_vertices()

    # Mirror across X = 0 — reflect verts.x then flip face winding so normals
    # point outward instead of inward.
    mirror = half.copy()
    mirror.vertices[:, 0] *= -1
    mirror.faces = mirror.faces[:, [0, 2, 1]]

    sym = trimesh.util.concatenate([half, mirror])
    return sym


# ---------------------------------------------------------------------------
# Stage 5 — Merge close vertices (close hairline gaps from the mirror seam)
# ---------------------------------------------------------------------------
def _merge_close(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    try:
        # Merge vertices that are within 0.5 mm of each other in world units.
        # Mesh is normalized later by the caller, so this is in normalized
        # space — a small absolute threshold avoids degenerate triangles.
        mesh.merge_vertices(merge_tex=False, merge_norm=False, digits_vertex=4)
    except TypeError:
        # Old trimesh API
        try:
            mesh.merge_vertices()
        except Exception:
            pass
    return mesh


# ---------------------------------------------------------------------------
# Stage 6 — Humphrey smoothing (preserves volume)
# ---------------------------------------------------------------------------
def _smooth(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    iters = int(os.environ.get("SCS_TRIPOSR_SMOOTH_ITER", "5"))
    if iters <= 0:
        return mesh
    try:
        trimesh.smoothing.filter_humphrey(mesh, iterations=iters, beta=0.5)
    except Exception as e:
        print(f"[triposr-postproc] smoothing skipped: {e}", flush=True)
    return mesh


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def clean_triposr_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """End-to-end post-processing for a raw TripoSR output. Returns a cleaned
    Trimesh ready for scaling + PBR-colour application + GLB export.

    Idempotent in the worst case — every internal step gracefully degrades
    to a pass-through on error, so calling twice is safe."""
    mesh = _safe("filter_components", _filter_components_keep_legs, mesh)
    mesh = _safe("center", _center, mesh)
    mesh = _safe("orient_upright", _orient_upright, mesh)
    mesh = _safe("mirror_symmetry_x", _mirror_symmetry_x, mesh)
    mesh = _safe("merge_close", _merge_close, mesh)
    mesh = _safe("smooth", _smooth, mesh)
    return mesh
