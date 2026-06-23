"""
eval_bakeoff.py — scale the photo->3D accuracy eval across many objects AND the four
generators (TripoSR / InstantMesh / TRELLIS / SAM 3D). Reuses eval_accuracy (Chamfer +
F-score), so cloud bake-off results are scored with the exact same, validated metric.

Two subcommands:

  photos   Render GT photos from ABO meshes + write manifest.json (object_id -> gt mesh,
           photo). Upload bakeoff_in/ to RunPod and run cloud/compare_4way.sh per photo.
             python eval_bakeoff.py photos --categories office_chair,desk,table --n 5

  score    Score a directory of reconstructions against ABO ground truth and emit a
           model x metric comparison table + bar-chart figure. Expects, per object:
               <recons>/<object_id>/<model>.glb     (model in triposr|instantmesh|trellis|sam3d)
             python eval_bakeoff.py score --recons bakeoff_out --manifest bakeoff_in/manifest.json

The same `score` step works on local TripoSR runs (eval_photo3d.py output) and on the
downloaded RunPod comparison folder.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
ABO = REPO / "data" / "mesh_library_abo"

import eval_accuracy   # noqa: E402

MODELS = ["triposr", "instantmesh", "trellis", "sam3d"]


def cmd_photos(args):
    import trimesh
    out = Path(args.out); (out / "photos").mkdir(parents=True, exist_ok=True)
    man = json.loads((ABO / "manifest.json").read_text(encoding="utf-8"))
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    manifest = []
    for cat in cats:
        items = [e for e in man if e.get("category") == cat][: args.n]
        for e in items:
            oid = e["id"]; gt = ABO / e["glb"]
            s = trimesh.load(str(gt))
            scene = s if isinstance(s, trimesh.Scene) else s.scene()
            scene.set_camera(angles=(np.radians(25), np.radians(-35), 0))
            png = out / "photos" / f"{oid}.png"
            png.write_bytes(scene.save_image(resolution=(args.res, args.res), visible=True))
            manifest.append({"object_id": oid, "category": cat,
                             "gt_glb": str(gt), "photo": str(png)})
            print(f"  rendered {oid}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)} photos -> {out}/photos/  + manifest.json")
    print("Next: upload to RunPod, run cloud/compare_4way.sh per photo (output per object_id),")
    print("      download results, then: eval_bakeoff.py score --recons <dir> --manifest manifest.json")


def _find_recon(recons: Path, oid: str, model: str):
    for cand in (recons / oid / f"{model}.glb", recons / oid / "recon.glb",
                 recons / f"{oid}_{model}.glb"):
        if cand.exists():
            return cand
    return None


def cmd_score(args):
    recons = Path(args.recons)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    models = args.models.split(",") if args.models else MODELS

    rows = []   # (object_id, model, metrics)
    for entry in manifest:
        oid, gt_glb = entry["object_id"], entry["gt_glb"]
        try:
            gt = eval_accuracy.load_mesh(gt_glb)
        except Exception as exc:
            print(f"  GT load failed {oid}: {exc}"); continue
        for model in models:
            rc = _find_recon(recons, oid, model)
            if not rc:
                continue
            try:
                m = eval_accuracy.evaluate(gt, eval_accuracy.load_mesh(rc), n=args.samples)
                rows.append({"object_id": oid, "category": entry.get("category", "?"),
                             "model": model, **m})
                print(f"  {oid:28} {model:11} chamfer={m['chamfer']:.4f} F={m['fscore']:.3f}")
            except Exception as exc:
                print(f"  {oid} {model} FAILED: {exc}")

    (out / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    # aggregate per model
    agg = {}
    for r in rows:
        agg.setdefault(r["model"], []).append(r)
    summary = []
    for model in models:
        rs = agg.get(model, [])
        if not rs:
            continue
        ch = np.array([r["chamfer"] for r in rs]); fs = np.array([r["fscore"] for r in rs])
        pr = np.array([r["precision"] for r in rs]); re = np.array([r["recall"] for r in rs])
        summary.append({"model": model, "n": len(rs),
                        "chamfer_mean": round(float(ch.mean()), 4), "chamfer_std": round(float(ch.std()), 4),
                        "fscore_mean": round(float(fs.mean()), 3),
                        "precision_mean": round(float(pr.mean()), 3),
                        "recall_mean": round(float(re.mean()), 3)})

    md = ["# 4-way photo->3D accuracy (vs ABO ground truth)", "",
          "Same metric as `eval_accuracy.py` (Chamfer + F-score, normalised, multi-seed ICP).", "",
          "| model | n | chamfer (mean±std) | F@0.02 | precision | recall |",
          "|-------|---|--------------------|--------|-----------|--------|"]
    for s in summary:
        md.append(f"| {s['model']} | {s['n']} | {s['chamfer_mean']}±{s['chamfer_std']} "
                  f"| {s['fscore_mean']} | {s['precision_mean']} | {s['recall_mean']} |")
    md += ["", "_Lower chamfer = better; higher F-score = better. High precision + low recall "
               "= the single-view ceiling (visible surface captured, unseen back missed)._"]
    (out / "comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # bar chart: mean chamfer + F-score per model
    if summary:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        names = [s["model"] for s in summary]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
        a1.bar(names, [s["chamfer_mean"] for s in summary], color="#c0504d")
        a1.set_title("Mean Chamfer distance (lower = better)"); a1.set_ylabel("chamfer (norm)")
        a2.bar(names, [s["fscore_mean"] for s in summary], color="#4f81bd")
        a2.set_title("Mean F-score @0.02 (higher = better)"); a2.set_ylim(0, 1)
        for a in (a1, a2):
            a.tick_params(axis="x", rotation=15)
        fig.suptitle("Single-image -> 3D: 4-way accuracy on ABO ground truth", fontweight="bold")
        fig.tight_layout(); fig.savefig(out / "comparison_accuracy.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

    print(f"\n-> {out}/comparison.md + comparison.json + comparison_accuracy.png "
          f"({len(rows)} scored, {len(summary)} models)")


def main():
    ap = argparse.ArgumentParser(description="Scale photo->3D accuracy across objects + generators")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("photos", help="render GT photos + manifest for the cloud bake-off")
    p.add_argument("--categories", default="office_chair,desk,table")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--res", type=int, default=512)
    p.add_argument("--out", default=str(REPO / "bakeoff_in"))
    p.set_defaults(func=cmd_photos)

    p = sub.add_parser("score", help="score a recon directory vs ABO ground truth")
    p.add_argument("--recons", required=True, help="dir with <object_id>/<model>.glb")
    p.add_argument("--manifest", required=True, help="manifest.json from the photos step")
    p.add_argument("--models", default="", help="comma list (default: all four)")
    p.add_argument("--samples", type=int, default=30000)
    p.add_argument("--out", default=str(REPO / "bakeoff_out"))
    p.set_defaults(func=cmd_score)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
