"""optimize_ifc.py — analyze + optimize an IFC file's geometry. Works on ANY object(s).

Reads every IfcTriangulatedFaceSet in the IFC, cleans its mesh (drop floating debris → repair to
watertight → Taubin-smooth → decimate), writes the cleaner geometry back INTO the same IFC entities
(preserving hierarchy, placement, materials, metadata), and saves an optimized IFC + a before/after
report (products, face-sets, faces, vertices, entities, file size).

    python optimize_ifc.py <in.ifc> <out.ifc> [--target-faces 15000]

This is the executive's objective: an algorithm that operates ON the IFC data and makes every object
cleaner + lighter. Pure CPU.
"""
from __future__ import annotations
import sys, json, argparse, os
import numpy as np
import trimesh
import ifcopenshell


def _clean_mesh(verts, faces, target_faces):
    """Clean one object's mesh (verts Nx3, faces Mx3 0-based) -> (verts, faces). Guarded per stage."""
    mesh = trimesh.Trimesh(vertices=np.asarray(verts, float), faces=np.asarray(faces, int), process=False)
    # 1) debris removal — keep components that are >= 0.6% of the faces (drops floaters, keeps legs)
    try:
        comps = mesh.split(only_watertight=False)
        if len(comps) > 1:
            total = sum(len(c.faces) for c in comps)
            kept = [c for c in comps if len(c.faces) / total >= 0.006] \
                or [max(comps, key=lambda c: len(c.faces))]
            mesh = trimesh.util.concatenate(kept)
    except Exception:
        pass
    # 2) watertight repair (MeshFix) — join components, fill holes, fix manifold
    try:
        import pymeshfix
        vc, fc = pymeshfix.clean_from_arrays(
            np.asarray(mesh.vertices, np.float64), np.asarray(mesh.faces, np.int32),
            joincomp=True, remove_smallest_components=False)
        if len(vc) and len(fc):
            mesh = trimesh.Trimesh(vertices=vc, faces=fc, process=True)
    except Exception:
        pass
    # 3) Taubin smoothing (volume-preserving)
    try:
        trimesh.smoothing.filter_taubin(mesh, iterations=10)
    except Exception:
        pass
    # 4) decimation to a face budget
    try:
        if len(mesh.faces) > target_faces:
            import fast_simplification
            reduction = 1.0 - (target_faces / len(mesh.faces))
            v, f = fast_simplification.simplify(
                np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int32),
                target_reduction=float(reduction))
            mesh = trimesh.Trimesh(vertices=v, faces=f, process=True)
    except Exception:
        pass
    return np.asarray(mesh.vertices), np.asarray(mesh.faces)


def _analyze(ifc):
    fss = ifc.by_type("IfcTriangulatedFaceSet")
    faces = sum(len(fs.CoordIndex or []) for fs in fss)
    verts = sum(len(fs.Coordinates.CoordList or []) for fs in fss)
    return {"products": len(ifc.by_type("IfcProduct")), "face_sets": len(fss),
            "faces": int(faces), "vertices": int(verts), "entities": len(list(ifc))}


def optimize_ifc(in_path, out_path, target_faces=15000):
    ifc = ifcopenshell.open(in_path)
    before = _analyze(ifc); before["kb"] = os.path.getsize(in_path) // 1024

    cleaned, per_object = 0, []
    for fs in ifc.by_type("IfcTriangulatedFaceSet"):
        try:
            verts = np.array(fs.Coordinates.CoordList, dtype=float)
            faces = np.array(fs.CoordIndex, dtype=int) - 1          # IFC CoordIndex is 1-based
            f0 = len(faces)
            cv, cf = _clean_mesh(verts, faces, target_faces)
            if len(cv) >= 3 and len(cf) >= 1:
                old = fs.Coordinates
                fs.Coordinates = ifc.createIfcCartesianPointList3D(
                    CoordList=[tuple(float(x) for x in p) for p in cv])
                fs.CoordIndex = [tuple(int(i) + 1 for i in f) for f in cf]   # back to 1-based
                try:
                    ifc.remove(old)
                except Exception:
                    pass
                cleaned += 1
                per_object.append({"faces_before": int(f0), "faces_after": int(len(cf))})
        except Exception as e:
            per_object.append({"error": str(e)})

    ifc.write(out_path)
    after = _analyze(ifcopenshell.open(out_path)); after["kb"] = os.path.getsize(out_path) // 1024
    return {"ok": True, "face_sets_cleaned": cleaned,
            "before": before, "after": after,
            "faces_reduction_pct": round(100 * (1 - after["faces"] / max(before["faces"], 1)), 1),
            "size_reduction_pct": round(100 * (1 - after["kb"] / max(before["kb"], 1)), 1),
            "per_object": per_object[:20]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--target-faces", type=int, default=15000)
    args = ap.parse_args()
    print(json.dumps(optimize_ifc(args.inp, args.out, args.target_faces)))
