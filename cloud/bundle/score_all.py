"""score_all.py — score every model's meshes vs ground truth with the SAME metric.
Generic: scores out/<model>/<key>.glb against the manifest's gt for <key>. Used BOTH on
the pod (immediate cloud scores) and locally (final unified table incl. TripoSR baselines)
so every model is measured by the identical eval_accuracy call — no metric drift.

  python score_all.py manifest.json out [--n 30000] [--tau 0.02]

manifest.json: [{"key","gt", ...}], gt resolved relative to the manifest's directory.
out/: one subdir per model (out/trellis/<key>.glb, out/triposr_sam2/<key>.glb, ...).
Writes out/cloud_scores.csv + a per-model summary to stdout.
"""
import sys, os, json, csv, argparse, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_accuracy import evaluate, load_mesh   # the validated, shared metric

ap = argparse.ArgumentParser()
ap.add_argument("manifest"); ap.add_argument("out")
ap.add_argument("--n", type=int, default=30000)
ap.add_argument("--tau", type=float, default=0.02)
args = ap.parse_args()

man_dir = os.path.dirname(os.path.abspath(args.manifest))
items = json.load(open(args.manifest, encoding="utf-8"))
gt_of = {it["key"]: (it["gt"] if os.path.isabs(it["gt"]) else os.path.join(man_dir, it["gt"]))
         for it in items}
type_of = {it["key"]: it.get("type", "") for it in items}

models = sorted(d for d in os.listdir(args.out)
                if os.path.isdir(os.path.join(args.out, d)) and not d.startswith("_"))
print(f"scoring models: {models}")

rows, summ = [], {}
for m in models:
    fs, chs = [], []
    for key, gt in gt_of.items():
        glb = os.path.join(args.out, m, key + ".glb")
        if not os.path.exists(glb):
            rows.append({"model": m, "key": key, "type": type_of[key],
                         "status": "missing", "chamfer": "", "fscore": "",
                         "precision": "", "recall": ""})
            continue
        try:
            r = evaluate(load_mesh(gt), load_mesh(glb), n=args.n, tau=args.tau)
            rows.append({"model": m, "key": key, "type": type_of[key], "status": "ok",
                         "chamfer": r["chamfer"], "fscore": r["fscore"],
                         "precision": r["precision"], "recall": r["recall"]})
            fs.append(r["fscore"]); chs.append(r["chamfer"])
        except Exception as e:
            print(f"  score FAIL {m}/{key}: {e!r}")
            rows.append({"model": m, "key": key, "type": type_of[key],
                         "status": "error", "chamfer": "", "fscore": "",
                         "precision": "", "recall": ""})
    summ[m] = (sum(fs)/len(fs) if fs else 0.0, sum(chs)/len(chs) if chs else 0.0, len(fs))

csv_path = os.path.join(args.out, "cloud_scores.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["model", "key", "type", "status",
                                      "chamfer", "fscore", "precision", "recall"])
    w.writeheader(); w.writerows(rows)

print(f"\n=== mean scores (n={args.n}, tau={args.tau}) ===")
print(f"{'model':18} {'mean F':>8} {'mean Chamfer':>13} {'scored':>7}")
for m, (mf, mc, k) in sorted(summ.items(), key=lambda x: -x[1][0]):
    print(f"{m:18} {mf:8.3f} {mc:13.4f} {k:7d}")
print(f"\nwrote {csv_path}")
