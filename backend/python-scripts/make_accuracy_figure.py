"""
make_accuracy_figure.py — paper figure for the photo->3D accuracy result.

Reads eval_out/results.json (from eval_photo3d.py) and renders a two-panel figure
that tells the single-view-ceiling story graphically:
  left  — per-object Chamfer distance vs the self-test reference lines (identity / different-object)
  right — precision vs recall per object (the gap = unseen surface the model can't recover)

Out: paper_figures/fig09_accuracy_triposr.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval_out" / "results.json"
OUT = REPO / "paper_figures" / "fig09_accuracy_triposr.png"

# reference chamfer levels from eval_accuracy --selftest (calibration anchors)
REF_IDENTITY = 0.009
REF_DIFFERENT = 0.151


def main():
    if not RESULTS.exists():
        sys.exit(f"no results at {RESULTS} — run: python eval_photo3d.py --category office_chair --n 3")
    rows = [r for r in json.loads(RESULTS.read_text(encoding="utf-8")) if "chamfer" in r]
    if not rows:
        sys.exit("no scored rows in results.json")
    labels = [r["id"].split("_")[-1] for r in rows]
    chamfer = [r["chamfer"] for r in rows]
    prec = [r["precision"] for r in rows]
    rec = [r["recall"] for r in rows]
    x = np.arange(len(rows))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))

    a1.bar(x, chamfer, color="#c0504d", width=0.6)
    a1.axhline(REF_IDENTITY, ls="--", color="#2e7d32", lw=1.2, label=f"identity ({REF_IDENTITY})")
    a1.axhline(REF_DIFFERENT, ls="--", color="#888", lw=1.2, label=f"different object ({REF_DIFFERENT})")
    a1.set_xticks(x); a1.set_xticklabels(labels, rotation=15)
    a1.set_ylabel("Chamfer distance (normalised)")
    a1.set_title("TripoSR reconstruction error vs reference", fontweight="bold")
    a1.legend(fontsize=9)

    w = 0.38
    a2.bar(x - w / 2, prec, w, label="precision (recon near GT)", color="#4f81bd")
    a2.bar(x + w / 2, rec, w, label="recall (GT covered)", color="#e0a030")
    a2.set_xticks(x); a2.set_xticklabels(labels, rotation=15)
    a2.set_ylim(0, 1); a2.set_ylabel("fraction within tau=0.02")
    a2.set_title("The single-view ceiling: precision >> recall", fontweight="bold")
    a2.legend(fontsize=9)

    fig.suptitle("Single-image -> 3D accuracy (TripoSR vs ABO ground truth)",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, bbox_inches="tight"); plt.close(fig)
    print(f"-> {OUT}  ({len(rows)} objects, mean chamfer {np.mean(chamfer):.3f}, "
          f"mean precision {np.mean(prec):.2f} vs recall {np.mean(rec):.2f})")


if __name__ == "__main__":
    main()
