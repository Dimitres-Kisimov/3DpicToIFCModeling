"""clean_and_optimize.py — repair + optimize a generated mesh for clean BIM output.

Turns messy TripoSR output (floating debris, holes, non-manifold, noisy surface) into a clean,
watertight, optimized mesh. Each stage is guarded so one failure never crashes the pass.

Pipeline:
  1. debris removal    — drop tiny isolated floating components (keeps the real body + big parts)
  2. watertight repair — pymeshfix (MeshFix): join components, fill holes, fix self-intersections
  3. Taubin smoothing  — volume-preserving smooth (won't shrink the mesh like Laplacian)
  4. decimation        — fast_simplification to a face budget (smaller / faster IFC)
  5. ground + centre   — sit flat on Y=0, centred on X/Z

    python clean_and_optimize.py <in.glb> <out.glb> [--target-faces 15000] [--solidify]

--solidify swaps stages 1-2 for a voxel remesh: merges everything (incl. detached legs) into ONE
watertight solid. Cleaner + connected, but blobs thin features. Use when the base is fragmented.
"""
from __future__ import annotations
import sys, json, argparse, os
import numpy as np
import trimesh


def _capture_color(mesh):
    """Grab the original mesh's base colour (PBR baseColorFactor, else mean vertex colour)."""
    try:
        mat = getattr(mesh.visual, "material", None)
        bcf = getattr(mat, "baseColorFactor", None) if mat is not None else None
        if bcf is not None:
            c = np.array(bcf, dtype=float)
            return c if c.max() <= 1.0 else c / 255.0
    except Exception:
        pass
    try:
        vc = mesh.visual.vertex_colors
        if vc is not None and len(vc):
            return np.array(vc, dtype=float).mean(axis=0) / 255.0
    except Exception:
        pass
    return None


def _apply_color(mesh, color):
    """Re-attach the captured colour as a PBR material so xeokit renders it."""
    if color is None:
        return mesh
    try:
        from trimesh.visual.material import PBRMaterial
        rgba = np.clip(np.asarray(color, dtype=float), 0, 1)
        if len(rgba) == 3:
            rgba = np.append(rgba, 1.0)
        mesh.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(baseColorFactor=rgba))
    except Exception:
        pass
    return mesh


def _stats(mesh):
    try:
        comps = len(mesh.split(only_watertight=False))
    except Exception:
        comps = -1
    return {"faces": int(len(mesh.faces)), "vertices": int(len(mesh.vertices)),
            "components": comps, "watertight": bool(mesh.is_watertight)}


def _debris_filter(mesh, min_ratio=0.006):
    """Keep components that are >= min_ratio of total faces (0.6% keeps legs, drops true debris)."""
    comps = mesh.split(only_watertight=False)
    if len(comps) <= 1:
        return mesh, 0
    total = sum(len(c.faces) for c in comps)
    kept = [c for c in comps if len(c.faces) / total >= min_ratio]
    dropped = len(comps) - len(kept)
    if not kept:
        kept = [max(comps, key=lambda c: len(c.faces))]
    return trimesh.util.concatenate(kept), dropped


def _voxel_solidify(mesh, pitch_frac=0.012):
    """Remesh into ONE watertight solid via voxelization — merges detached parts, kills debris."""
    extent = float(mesh.extents.max())
    pitch = max(extent * pitch_frac, 1e-4)
    vox = mesh.voxelized(pitch).fill()
    solid = vox.marching_cubes
    solid.merge_vertices()
    return solid


def clean_mesh(mesh, target_faces=15000, solidify=False, ground=True):
    """THE single geometry-cleanup pass — shared by GLB export AND IFC optimize (written once).
    debris removal -> MeshFix watertight -> Taubin smooth -> quadric decimate [-> ground].
    Returns (cleaned_mesh, stages_dict)."""
    stages = {}
    if solidify:
        try:
            mesh = _voxel_solidify(mesh); stages["solidify"] = "voxel remesh"
        except Exception as e:
            stages["solidify_error"] = str(e)
    else:
        try:
            mesh, dropped = _debris_filter(mesh); stages["debris_removed_components"] = dropped
        except Exception as e:
            stages["debris_error"] = str(e)
        try:
            import pymeshfix
            vc, fc = pymeshfix.clean_from_arrays(
                np.asarray(mesh.vertices, np.float64), np.asarray(mesh.faces, np.int32),
                joincomp=True, remove_smallest_components=False)
            if len(vc) and len(fc):
                mesh = trimesh.Trimesh(vertices=vc, faces=fc, process=True)
                stages["watertight_repair"] = "pymeshfix"
        except Exception as e:
            stages["repair_error"] = str(e)
    try:
        trimesh.smoothing.filter_taubin(mesh, iterations=12); stages["smoothing"] = "taubin x12"
    except Exception as e:
        stages["smooth_error"] = str(e)
    try:
        if len(mesh.faces) > target_faces:
            import fast_simplification
            reduction = 1.0 - (target_faces / len(mesh.faces))
            vs, fs = fast_simplification.simplify(
                np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int32),
                target_reduction=float(reduction))
            mesh = trimesh.Trimesh(vertices=vs, faces=fs, process=True)
            stages["decimated_to_faces"] = int(len(mesh.faces))
    except Exception as e:
        stages["decimate_error"] = str(e)
    if ground:
        try:
            b = mesh.bounds
            mesh.apply_translation([-(b[0][0] + b[1][0]) / 2, -b[0][1], -(b[0][2] + b[1][2]) / 2])
        except Exception:
            pass
    return mesh, stages


def clean_and_optimize(in_path, out_path, target_faces=15000, solidify=False):
    report = {"stages": {}}
    mesh = trimesh.load(in_path, force="mesh")
    color = _capture_color(mesh)          # keep the original colour through the rebuild
    report["before"] = _stats(mesh)

    mesh, report["stages"] = clean_mesh(mesh, target_faces, solidify)   # THE shared cleanup (once)
    _apply_color(mesh, color)             # re-attach the captured colour before export
    mesh.export(out_path)
    report["after"] = _stats(mesh)
    report["after"]["kb"] = os.path.getsize(out_path) // 1024
    report["ok"] = True
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--target-faces", type=int, default=15000)
    ap.add_argument("--solidify", action="store_true")
    args = ap.parse_args()
    print(json.dumps(clean_and_optimize(args.inp, args.out, args.target_faces, args.solidify)))
