"""
eval_accuracy.py — geometric accuracy of a reconstructed mesh vs ground truth.

This is the measurement harness for the paper's photo->3D accuracy claim. It is
generator-agnostic: feed it a ground-truth mesh and any reconstruction (TripoSR /
InstantMesh / TRELLIS / SAM 3D output) and it returns scale/pose-normalised metrics.

Why ABO-as-ground-truth: we own 400 real product meshes, so we can render one to a
synthetic photo, reconstruct it, and compare the result back to the *known* original.
That yields hard accuracy numbers most papers cannot produce cleanly.

Metrics (both meshes centred at origin + scaled to unit bbox-diagonal, optional ICP):
  - Chamfer distance: mean bidirectional nearest-neighbour distance (lower = better)
  - F-score @ tau:    harmonic mean of precision/recall of points within tau of the
                      other surface (higher = better; tau in normalised units)

Usage:
  python eval_accuracy.py <ground_truth.glb> <reconstruction.glb> [--n 50000] [--tau 0.02] [--no-align]
  python eval_accuracy.py --selftest        # validate the metric on degraded ABO meshes
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def load_mesh(path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate([g for g in m.geometry.values()
                                      if isinstance(g, trimesh.Trimesh)])
    if m is None or len(m.vertices) == 0:
        raise ValueError(f"empty mesh: {path}")
    return m


def normalize(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Centre at origin and scale so the bounding-box diagonal == 1 (unit, pose-fixed
    only for translation+scale; rotation handled separately by ICP)."""
    m = mesh.copy()
    m.apply_translation(-m.bounding_box.centroid)
    diag = float(np.linalg.norm(m.extents))
    if diag > 1e-9:
        m.apply_scale(1.0 / diag)
    return m


def _seed_rotations():
    """Coarse initial orientations to seed ICP — reconstructions come out in an
    arbitrary canonical frame (commonly yaw-rotated or flipped), and ICP only
    refines locally, so we must try several starts and keep the best."""
    seeds = []
    for axis in ([0, 1, 0], [1, 0, 0], [0, 0, 1]):
        for ang in (0.0, np.pi / 2, np.pi, 3 * np.pi / 2):
            seeds.append(trimesh.transformations.rotation_matrix(ang, axis))
    return seeds


def _icp_align(src: trimesh.Trimesh, dst: trimesh.Trimesh, n=3000) -> trimesh.Trimesh:
    """Align src onto dst: try several seed rotations, ICP-refine each, keep the one
    whose points sit closest to dst (robust to arbitrary reconstruction pose)."""
    dst_pts = dst.sample(n)
    dtree = cKDTree(dst_pts)
    best_T, best_err = np.eye(4), np.inf
    for R in _seed_rotations():
        try:
            sp = trimesh.transform_points(src.sample(n), R)
            T, _, _ = trimesh.registration.icp(sp, dst_pts, max_iterations=30)
            moved = trimesh.transform_points(sp, T)
            err = float(dtree.query(moved)[0].mean())
            if err < best_err:
                best_err, best_T = err, T @ R
        except Exception:
            continue
    out = src.copy(); out.apply_transform(best_T)
    return out


def _metrics(a_pts, b_pts, tau):
    ta, tb = cKDTree(a_pts), cKDTree(b_pts)
    da, _ = tb.query(a_pts)   # a -> nearest b
    db, _ = ta.query(b_pts)   # b -> nearest a
    chamfer = float(da.mean() + db.mean())          # bidirectional
    precision = float((da < tau).mean())            # recon points near GT
    recall = float((db < tau).mean())               # GT points covered by recon
    f = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return {"chamfer": round(chamfer, 6),
            "fscore": round(f, 4), "precision": round(precision, 4), "recall": round(recall, 4),
            "acc_mean": round(float(da.mean()), 6), "cov_mean": round(float(db.mean()), 6)}


def evaluate(gt_mesh, recon_mesh, n=50000, tau=0.02, align=True, seed=0) -> dict:
    np.random.seed(seed)   # deterministic surface sampling -> reproducible metrics
    gt = normalize(gt_mesh)
    rc = normalize(recon_mesh)
    if align:
        rc = _icp_align(rc, gt)
    a = np.asarray(rc.sample(n))    # reconstruction surface
    b = np.asarray(gt.sample(n))    # ground-truth surface
    out = _metrics(a, b, tau)
    out.update({"n": n, "tau": tau, "aligned": align})
    return out


def _selftest():
    """Validate the metric is well-behaved using ABO meshes as both GT and degraded
    'reconstructions': identity ~0 chamfer / F~1; noise & decimation worsen smoothly;
    a different object scores far worse. No generator/GPU needed."""
    repo = Path(__file__).resolve().parents[2]
    abo = repo / "data" / "mesh_library_abo"
    man = json.loads((abo / "manifest.json").read_text(encoding="utf-8"))
    chairs = [e for e in man if e.get("category") == "office_chair"]
    gt = load_mesh(abo / chairs[0]["glb"])
    other = load_mesh(abo / chairs[1]["glb"])

    # degraded copies of the ground truth
    noisy = gt.copy()
    rng = np.random.default_rng(0)
    scale = float(np.linalg.norm(noisy.extents))
    noisy.vertices = noisy.vertices + rng.normal(0, 0.01 * scale, noisy.vertices.shape)
    try:
        deci = gt.simplify_quadric_decimation(face_count=max(50, len(gt.faces) // 20))
    except Exception:
        deci = gt.copy()

    cases = [("identity (gt vs gt)", gt),
             ("decimated 20x", deci),
             ("noisy 1% bbox", noisy),
             ("different chair", other)]
    print(f"{'case':22} {'chamfer':>10} {'F@0.02':>8} {'precision':>10} {'recall':>8}")
    rows = []
    for name, recon in cases:
        m = evaluate(gt, recon, n=20000, tau=0.02, align=(name != "identity (gt vs gt)"))
        print(f"{name:22} {m['chamfer']:10.5f} {m['fscore']:8.3f} {m['precision']:10.3f} {m['recall']:8.3f}")
        rows.append({"case": name, **m})

    ok = (rows[0]["chamfer"] < rows[3]["chamfer"] and rows[0]["fscore"] > 0.9
          and rows[3]["fscore"] < rows[0]["fscore"])
    print("\nSELFTEST", "PASS" if ok else "FAIL",
          "— identity best, different-object worst, F monotone-ish.")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Chamfer / F-score accuracy vs ground truth")
    ap.add_argument("gt", nargs="?", help="ground-truth mesh (e.g. an ABO .glb)")
    ap.add_argument("recon", nargs="?", help="reconstructed mesh")
    ap.add_argument("--n", type=int, default=50000, help="surface samples per mesh")
    ap.add_argument("--tau", type=float, default=0.02, help="F-score distance threshold (norm units)")
    ap.add_argument("--no-align", action="store_true", help="skip ICP pose alignment")
    ap.add_argument("--selftest", action="store_true", help="run metric validation on ABO meshes")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.gt or not args.recon:
        ap.error("provide <gt> <recon>, or --selftest")
    res = evaluate(load_mesh(args.gt), load_mesh(args.recon),
                   n=args.n, tau=args.tau, align=not args.no_align)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
