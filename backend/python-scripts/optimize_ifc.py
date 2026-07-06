"""optimize_ifc.py — ONE-pass IFC optimizer. Runs on any IFC (single object OR a whole building).

Efficiency by design — no process is repeated:
  1. clean geometry — the SHARED clean_mesh() (debris/spike -> MeshFix -> Taubin -> decimate).
                      Each UNIQUE mesh is cleaned ONCE (cached by geometry hash), not per instance.
  2. instance       — identical furniture meshes are stored ONCE and referenced N times (dup
                      IfcTriangulatedFaceSets are collapsed into one shared entity).
  3. precision      — CoordList rounded to N decimals (0.1 mm) -> smaller STEP text.
Writes an optimized IFC + before/after report. Optional gzip (.ifcZIP-style).

    python optimize_ifc.py <in.ifc> <out.ifc> [--target-faces 15000] [--no-clean] [--zip]
"""
from __future__ import annotations
import sys, json, argparse, os, hashlib, gzip
import numpy as np
import trimesh
import ifcopenshell

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_and_optimize import clean_mesh   # THE shared cleanup — never re-implemented


def _analyze(ifc):
    fss = ifc.by_type("IfcTriangulatedFaceSet")
    return {"products": len(ifc.by_type("IfcProduct")), "face_sets": len(fss),
            "faces": int(sum(len(fs.CoordIndex or []) for fs in fss)),
            "vertices": int(sum(len(fs.Coordinates.CoordList or []) for fs in fss)),
            "entities": len(list(ifc))}


def _geo_hash(fs):
    v = np.round(np.array(fs.Coordinates.CoordList, dtype=float), 3)
    f = np.array(fs.CoordIndex, dtype=int)
    return hashlib.md5(v.tobytes() + f.tobytes()).hexdigest()


def _repoint(ifc, dup, keep):
    """Replace every reference to `dup` with `keep` (direct or inside a list attribute)."""
    for inv in ifc.get_inverse(dup):
        for i in range(len(inv)):
            v = inv[i]
            if v is dup:
                inv[i] = keep
            elif isinstance(v, (list, tuple)) and any(x is dup for x in v):
                inv[i] = [keep if x is dup else x for x in v]


def optimize_ifc(in_path, out_path, target_faces=15000, do_clean=True, precision=4, make_zip=False):
    ifc = ifcopenshell.open(in_path)
    before = _analyze(ifc); before["kb"] = os.path.getsize(in_path) // 1024

    # 1) CLEAN — each unique mesh cleaned ONCE (cache), then precision-rounded on write-back
    cleaned, cache = 0, {}
    for fs in ifc.by_type("IfcTriangulatedFaceSet"):
        try:
            h = _geo_hash(fs)
            if do_clean:
                if h in cache:
                    cv, cf = cache[h]
                else:
                    verts = np.array(fs.Coordinates.CoordList, dtype=float)
                    faces = np.array(fs.CoordIndex, dtype=int) - 1        # IFC is 1-based
                    m, _ = clean_mesh(trimesh.Trimesh(verts, faces, process=False),
                                      target_faces, ground=False)
                    cv, cf = np.asarray(m.vertices), np.asarray(m.faces)
                    cache[h] = (cv, cf)
                if len(cv) < 3 or len(cf) < 1:
                    continue
            else:
                cv = np.array(fs.Coordinates.CoordList, dtype=float)
                cf = np.array(fs.CoordIndex, dtype=int) - 1
            old = fs.Coordinates
            fs.Coordinates = ifc.createIfcCartesianPointList3D(
                CoordList=[tuple(round(float(x), precision) for x in p) for p in cv])
            fs.CoordIndex = [tuple(int(i) + 1 for i in f) for f in cf]
            try: ifc.remove(old)
            except Exception: pass
            cleaned += 1
        except Exception:
            pass

    # 2) INSTANCE — collapse identical face-sets into one shared entity (store once, ref N times)
    instanced, groups = 0, {}
    for fs in ifc.by_type("IfcTriangulatedFaceSet"):
        groups.setdefault(_geo_hash(fs), []).append(fs)
    for h, fss in groups.items():
        if len(fss) > 1:
            keep = fss[0]
            for dup in fss[1:]:
                try:
                    oldc = dup.Coordinates
                    _repoint(ifc, dup, keep)
                    ifc.remove(dup)
                    try: ifc.remove(oldc)
                    except Exception: pass
                    instanced += 1
                except Exception:
                    pass

    ifc.write(out_path)
    after = _analyze(ifcopenshell.open(out_path)); after["kb"] = os.path.getsize(out_path) // 1024
    result = {"ok": True, "unique_meshes": len(cache) or None, "geometry_cleaned": cleaned,
              "meshes_instanced_away": instanced, "before": before, "after": after,
              "faces_reduction_pct": round(100 * (1 - after["faces"] / max(before["faces"], 1)), 1),
              "size_reduction_pct": round(100 * (1 - after["kb"] / max(before["kb"], 1)), 1)}
    if make_zip:
        zp = out_path + "Z"
        with open(out_path, "rb") as fh:
            gzdata = gzip.compress(fh.read(), 9)
        with open(zp, "wb") as fh:
            fh.write(gzdata)
        result["zip_kb"] = os.path.getsize(zp) // 1024
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--target-faces", type=int, default=15000)
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--zip", action="store_true")
    args = ap.parse_args()
    print(json.dumps(optimize_ifc(args.inp, args.out, args.target_faces,
                                  do_clean=not args.no_clean, make_zip=args.zip)))
