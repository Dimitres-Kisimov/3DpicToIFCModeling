"""Score each TripoSR reconstruction (SAM2, rembg) against its ABO ground-truth
mesh — Chamfer + F-score@0.02 — to objectively answer 'which is better'."""
import json, sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]
OUT = REPO / "outputs" / (sys.argv[1] if len(sys.argv) > 1 else "abo_test")

import eval_accuracy as ea

res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
rows = []
agg = defaultdict(lambda: {"sam_c": [], "sam_f": [], "rem_c": [], "rem_f": []})

for r in res["results"]:
    b, t = r["base"], r["type"]
    try:
        gt = ea.load_mesh(OUT / f"{b}_abo.glb")
        sam = ea.load_mesh(OUT / f"{b}_sam2.glb")
        rem = ea.load_mesh(OUT / f"{b}_rembg.glb")
        ms = ea.evaluate(gt, sam, n=20000)
        mr = ea.evaluate(gt, rem, n=20000)
        rows.append({"type": t, "base": b, "sam": ms, "rem": mr})
        agg[t]["sam_c"].append(ms["chamfer"]); agg[t]["sam_f"].append(ms["fscore"])
        agg[t]["rem_c"].append(mr["chamfer"]); agg[t]["rem_f"].append(mr["fscore"])
        print(f"{b:18} SAM2 chamfer={ms['chamfer']:.4f} F={ms['fscore']:.3f}  |  "
              f"rembg chamfer={mr['chamfer']:.4f} F={mr['fscore']:.3f}", flush=True)
    except Exception as e:
        print(f"{b}: FAILED {e}", flush=True)

def mean(x): return sum(x) / len(x) if x else float("nan")

print("\n==== BY TYPE (lower chamfer = better, higher F = better) ====")
print(f"{'type':14} {'SAM2 chamfer':>13} {'SAM2 F':>8} {'rembg chamfer':>14} {'rembg F':>8}")
allc_s, allf_s, allc_r, allf_r = [], [], [], []
for t, d in agg.items():
    print(f"{t:14} {mean(d['sam_c']):13.4f} {mean(d['sam_f']):8.3f} "
          f"{mean(d['rem_c']):14.4f} {mean(d['rem_f']):8.3f}")
    allc_s += d["sam_c"]; allf_s += d["sam_f"]; allc_r += d["rem_c"]; allf_r += d["rem_f"]
print(f"{'OVERALL':14} {mean(allc_s):13.4f} {mean(allf_s):8.3f} "
      f"{mean(allc_r):14.4f} {mean(allf_r):8.3f}")

(OUT / "scores.json").write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
print(f"\nwrote {OUT/'scores.json'}")
