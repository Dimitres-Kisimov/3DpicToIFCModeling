"""make_paper_figures.py — publication figures from the project's real benchmark data.

Fig 1  Study A: 5-AI single-image accuracy (mean F-score@0.02) vs the real
       catalog mesh reference. Values from deliverable/CLOUD_BENCHMARK_FINDINGS.md
       (H200 run, 2026-06-30..07-01).
Fig 2  Study B: archetype repair packs, silhouette-IoU before/after per category,
       aggregated live from benchmark/results/list*/<cat>/metrics.json (170 items).

Design: dataviz-skill reference palette (light surface #fcfcfb) — one blue series
#2a78d6, neutral gray reference #898781, hairline grid #e1e0d9, direct labels on
every mark (identity never carried by color alone).

    python make_paper_figures.py     -> docs/figures/*.png (200 dpi) + means CSV
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
OUT = HERE.parent / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK, INK2, MUT = "#0b0b0b", "#52514e", "#898781"
BLUE, GRID, BASE, SURF = "#2a78d6", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "text.color": INK, "axes.edgecolor": BASE, "axes.labelcolor": INK2,
    "xtick.color": MUT, "ytick.color": INK2, "figure.facecolor": SURF,
    "axes.facecolor": SURF, "savefig.facecolor": SURF,
})


def style_axes(ax, xgrid=True):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    if xgrid:
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
    ax.tick_params(length=0)


# ---------------------------------------------------------------- Fig 1: Study A
STUDY_A = [  # (label, mean F@0.02, is_reference)
    ("Real catalog mesh (ABO)", 1.000, True),
    ("TripoSG (VAST-AI, MIT)", 0.393, False),
    ("SAM 3D Objects (Meta)", 0.368, False),
    ("TRELLIS-image-large (MS, MIT)", 0.347, False),
    ("InstantMesh (TencentARC)*", 0.328, False),
    ("TripoSR · rembg (baseline)", 0.295, False),
    ("TripoSR · SAM2 (baseline)", 0.278, False),
]

fig, ax = plt.subplots(figsize=(7.6, 3.9))
rows = list(reversed(STUDY_A))
ys = range(len(rows))
for y, (label, val, ref) in zip(ys, rows):
    ax.barh(y, val, height=0.62, color=MUT if ref else BLUE, zorder=3)
    ax.text(val + 0.015, y, f"{val:.3f}", va="center", ha="left",
            fontsize=9.5, color=INK, fontweight="bold")
ax.set_yticks(list(ys))
ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
ax.set_xlim(0, 1.12)
ax.set_xlabel("mean F-score @ τ = 0.02 (10 furniture items, single front-view image, seed 42)",
              fontsize=8.5)
ax.set_title("Study A — single-image 3D accuracy: retrieval beats the best generator ≈ 2.5×",
             fontsize=11, loc="left", color=INK, pad=12)
style_axes(ax)
fig.text(0.005, 0.005,
         "H200 pod, identical inputs + scorer (Chamfer + F@0.02, ICP). "
         "*InstantMesh: benchmark-only (CC-BY-NC Zero123++ dependency).",
         fontsize=7.2, color=MUT)
fig.tight_layout(rect=(0, 0.035, 1, 1))
fig.savefig(OUT / "fig_study_a_fscores.png", dpi=200)
plt.close(fig)
print("fig 1 written")

# ---------------------------------------------------------------- Fig 2: Study B
cats: dict[str, dict[str, list[float]]] = {}
faces = {"raw": [], "improved": []}
wt = {"raw": [], "improved": []}
for mp in sorted(RES.glob("list*/*/metrics.json")):
    cat = mp.parent.name
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        continue
    for variant in ("raw", "improved"):
        v = m.get(variant) or {}
        if v.get("iou") is not None:
            cats.setdefault(cat, {"raw": [], "improved": []})[variant].append(float(v["iou"]))
        if v.get("faces"):
            faces[variant].append(float(v["faces"]))
        if v.get("watertight") is not None:
            wt[variant].append(1.0 if v["watertight"] else 0.0)

mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
agg = sorted(((c, mean(d["raw"]), mean(d["improved"])) for c, d in cats.items()
              if d["raw"] and d["improved"]), key=lambda r: r[2])

with (OUT / "study_b_category_means.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["category", "mean_iou_raw", "mean_iou_improved", "n_items"])
    for c, r, i in agg:
        w.writerow([c, f"{r:.3f}", f"{i:.3f}", len(cats[c]["raw"])])

fig, ax = plt.subplots(figsize=(7.6, 6.8))
for y, (c, r, i) in enumerate(agg):
    ax.plot([r, i], [y, y], color=GRID, linewidth=1.6, zorder=2)
    ax.plot(r, y, "o", color=MUT, markersize=8, zorder=3)
    ax.plot(i, y, "o", color=BLUE, markersize=8, zorder=4)
ax.set_yticks(range(len(agg)))
ax.set_yticklabels([c.replace("_", " ") for c, *_ in agg], fontsize=9.5)
ax.set_xlabel("mean silhouette IoU vs photo (best of 8 azimuths, 10 photos/category)", fontsize=8.5)
ax.set_title("Study B — archetype repair packs: silhouette IoU before → after, all 17 categories",
             fontsize=11, loc="left", color=INK, pad=12)
ax.plot([], [], "o", color=MUT, markersize=8, label="TripoSR raw")
ax.plot([], [], "o", color=BLUE, markersize=8, label="after repair packs (ours)")
ax.legend(loc="lower right", frameon=False, fontsize=9)
style_axes(ax)
fig.text(0.005, 0.005,
         f"170 internet photos (10 lists × 17 categories), RTX 4050, 2026-07-11.  "
         f"Mean faces {mean(faces['raw']):,.0f} → {mean(faces['improved']):,.0f} · "
         f"watertight {100*mean(wt['raw']):.0f}% → {100*mean(wt['improved']):.0f}%.",
         fontsize=7.2, color=MUT)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(OUT / "fig_study_b_repair_iou.png", dpi=200)
plt.close(fig)
print(f"fig 2 written ({len(agg)} categories, means CSV alongside)")
