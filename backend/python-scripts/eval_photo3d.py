"""
eval_photo3d.py — END-TO-END photo->3D accuracy on ABO ground truth.

For each ABO mesh:  render a synthetic photo  ->  TripoSR single-image reconstruction
->  Chamfer distance / F-score vs the ORIGINAL mesh (eval_accuracy).

This closes the paper's first-part loop and produces hard accuracy numbers, because
the ground-truth geometry is known (we own the ABO mesh we photographed).

Usage:
  python eval_photo3d.py --category office_chair --n 1     # prove the loop (1 object)
  python eval_photo3d.py --category office_chair --n 3     # small batch
Out: eval_out/<id>/photo.png, recon.glb ; eval_out/results.json + results.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
ABO = REPO / "data" / "mesh_library_abo"

import eval_accuracy   # noqa: E402


def render_photo(glb: Path, png: Path, res=512):
    """Render a clean 3/4 front-top synthetic photo of the mesh on a white background."""
    s = trimesh.load(str(glb))
    scene = s if isinstance(s, trimesh.Scene) else s.scene()
    scene.set_camera(angles=(np.radians(25), np.radians(-35), 0))
    data = scene.save_image(resolution=(res, res), visible=True)
    png.write_bytes(data)


def run_triposr(png: Path, out_glb: Path) -> bool:
    import run_triposr
    return bool(run_triposr.generate_mesh_triposr(str(png), str(out_glb)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="office_chair")
    ap.add_argument("--n", type=int, default=1, help="how many objects from the category")
    ap.add_argument("--out", default=str(REPO / "eval_out"))
    ap.add_argument("--samples", type=int, default=30000)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    man = json.loads((ABO / "manifest.json").read_text(encoding="utf-8"))
    items = [e for e in man if e.get("category") == args.category][: args.n]
    if not items:
        ap.error(f"no ABO meshes for category {args.category}")

    results = []
    for k, e in enumerate(items, 1):
        oid = e["id"]; gt_glb = ABO / e["glb"]
        d = out / oid; d.mkdir(exist_ok=True)
        photo, recon = d / "photo.png", d / "recon.glb"
        print(f"[{k}/{len(items)}] {oid}")
        t0 = time.time()
        try:
            render_photo(gt_glb, photo)
            print(f"  rendered photo ({photo.stat().st_size} B); running TripoSR ...")
            if not run_triposr(photo, recon):
                raise RuntimeError("TripoSR returned no mesh")
            secs = round(time.time() - t0, 1)
            m = eval_accuracy.evaluate(eval_accuracy.load_mesh(gt_glb),
                                       eval_accuracy.load_mesh(recon), n=args.samples)
            row = {"id": oid, "category": args.category, "seconds": secs,
                   "gt_faces": int(e.get("faces", 0)), **m}
            print(f"  chamfer={m['chamfer']:.4f}  F@{m['tau']}={m['fscore']:.3f}  "
                  f"(prec={m['precision']:.3f} rec={m['recall']:.3f})  {secs}s")
            results.append(row)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({"id": oid, "category": args.category, "error": str(exc)})

    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    ok = [r for r in results if "chamfer" in r]
    md = ["# Photo->3D accuracy (TripoSR vs ABO ground truth)", "",
          "| id | category | chamfer | F@0.02 | precision | recall | sec |",
          "|----|----------|---------|--------|-----------|--------|-----|"]
    for r in ok:
        md.append(f"| {r['id']} | {r['category']} | {r['chamfer']:.4f} | {r['fscore']:.3f} "
                  f"| {r['precision']:.3f} | {r['recall']:.3f} | {r['seconds']} |")
    if ok:
        ch = np.array([r["chamfer"] for r in ok]); fs = np.array([r["fscore"] for r in ok])
        md += ["", f"**Mean chamfer {ch.mean():.4f}, mean F-score {fs.mean():.3f} "
                   f"over {len(ok)} object(s).**"]
    (out / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n-> {out}/results.json + results.md  ({len(ok)}/{len(results)} scored)")


if __name__ == "__main__":
    main()
