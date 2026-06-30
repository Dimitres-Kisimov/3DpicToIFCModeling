"""
Collect every benchmark round into ONE place:
  - deliverable/all_scores.csv / all_scores.json  (every model, every round)
  - deliverable/round_summary.csv                 (per-round + per-type means)
  - MASTER_DASHBOARD.html (repo root)             (one page: summary table + links to all
                                                   galleries, the paper, the report, the bundles)
Re-run any time to refresh as new rounds (e.g. Poly Haven) get scored.
"""
from __future__ import annotations
import json, csv, statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUTPUTS = REPO / "outputs"

ROUNDS = [
    ("abo_test",          "ABO first-5 (renders)"),
    ("abo_test_random",   "ABO random seed-42 (renders)"),
    ("abo_test_cats",     "ABO new categories (cabinet/stool/lamp)"),
    ("abo_test_realphoto","ABO real product PHOTOS (seed-42)"),
    ("abo_test_polyhaven","Poly Haven CC0 (different dataset)"),
    ("abo_test_objaverse","Objaverse in-the-wild (research/internal-only)"),
]

# ---- gather every model row -------------------------------------------------
all_rows, summary = [], []
for folder, label in ROUNDS:
    sp = OUTPUTS / folder / "scores.json"
    if not sp.exists():
        summary.append({"round": folder, "label": label, "status": "not scored yet"})
        continue
    rows = json.loads(sp.read_text(encoding="utf-8"))["rows"]
    for r in rows:
        all_rows.append({"round": folder, "label": label, "type": r["type"], "base": r["base"],
                         "sam2_chamfer": r["sam"]["chamfer"], "sam2_fscore": r["sam"]["fscore"],
                         "rembg_chamfer": r["rem"]["chamfer"], "rembg_fscore": r["rem"]["fscore"]})
    summary.append({
        "round": folder, "label": label, "n": len(rows),
        "sam2_F": round(st.mean(r["sam"]["fscore"] for r in rows), 3),
        "rembg_F": round(st.mean(r["rem"]["fscore"] for r in rows), 3),
        "sam2_chamfer": round(st.mean(r["sam"]["chamfer"] for r in rows), 3),
        "rembg_chamfer": round(st.mean(r["rem"]["chamfer"] for r in rows), 3),
        "winner": "rembg" if st.mean(r["rem"]["fscore"] for r in rows) > st.mean(r["sam"]["fscore"] for r in rows) else "SAM2",
    })

DELI = REPO / "deliverable"
# per-model CSV + JSON
with open(DELI / "all_scores.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys())); w.writeheader(); w.writerows(all_rows)
(DELI / "all_scores.json").write_text(json.dumps({"rows": all_rows, "summary": summary}, indent=2), encoding="utf-8")
with open(DELI / "round_summary.csv", "w", newline="", encoding="utf-8") as f:
    cols = ["round", "label", "n", "sam2_F", "rembg_F", "sam2_chamfer", "rembg_chamfer", "winner"]
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    w.writerows([s for s in summary if "n" in s])

# ---- master dashboard html --------------------------------------------------
galleries = sorted((OUTPUTS).glob("view_*.html"))
bundles = sorted(DELI.glob("*.zip"))

def srow(s):
    if "n" not in s:
        return f'<tr><td>{s["label"]}</td><td colspan=6 style="color:#999">{s["status"]}</td></tr>'
    win = f'<b style="color:#2e7d32">{s["winner"]}</b>'
    return (f'<tr><td>{s["label"]}</td><td>{s["n"]}</td>'
            f'<td>{s["sam2_F"]:.3f}</td><td>{s["rembg_F"]:.3f}</td>'
            f'<td>{s["sam2_chamfer"]:.3f}</td><td>{s["rembg_chamfer"]:.3f}</td><td>{win}</td></tr>')

html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>SCS TripoSR Study — Master Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:24px 30px;color:#1a1a1a}}
h1{{border-bottom:2px solid #333;padding-bottom:6px}} h2{{margin-top:26px}}
table{{border-collapse:collapse;margin:10px 0;font-size:14px}} th,td{{border:1px solid #ccc;padding:6px 11px;text-align:left}} th{{background:#f0f0f0}}
a{{color:#1565c0;text-decoration:none}} a:hover{{text-decoration:underline}}
.cards{{display:flex;flex-wrap:wrap;gap:8px}} .card{{border:1px solid #ddd;border-radius:8px;padding:8px 12px;background:#fafafa}}
small{{color:#777}}
</style></head><body>
<h1>SCS Photo&rarr;3D Study &mdash; Master Dashboard</h1>
<p><small>One collected index of every benchmark round, gallery, document, and download produced in this study.</small></p>

<h2>Benchmark scoreboard (all rounds)</h2>
<p><small>F-score vs ground-truth mesh (higher=better); Chamfer (lower=better). Ground-truth mesh itself = F 1.000 in every row.</small></p>
<table><tr><th>Round</th><th>n</th><th>SAM2 F</th><th>rembg F</th><th>SAM2 Chamfer</th><th>rembg Chamfer</th><th>Winner</th></tr>
{chr(10).join(srow(s) for s in summary)}
</table>
<p><small>Raw per-model numbers: <a href="deliverable/all_scores.csv">all_scores.csv</a> &middot;
<a href="deliverable/all_scores.json">all_scores.json</a> &middot;
<a href="deliverable/round_summary.csv">round_summary.csv</a></small></p>

<h2>Interactive galleries (drag to orbit)</h2>
<div class="cards">
{chr(10).join(f'<div class="card"><a href="outputs/{g.name}">{g.stem}</a></div>' for g in galleries)}
</div>

<h2>Documents</h2>
<div class="cards">
<div class="card"><a href="PAPER_Single_View_Furniture_3D.html">Scientific paper (HTML)</a></div>
<div class="card"><a href="PAPER_Single_View_Furniture_3D.md">paper (markdown)</a></div>
<div class="card"><a href="SESSION_2026_06_30_TripoSR_INVESTIGATION_REPORT.html">Investigation report</a></div>
</div>

<h2>Portable download bundles (deliverable/)</h2>
<div class="cards">
{chr(10).join(f'<div class="card"><a href="deliverable/{b.name}">{b.name}</a> <small>{b.stat().st_size/1e6:.0f} MB</small></div>' for b in bundles)}
</div>
</body></html>"""
(REPO / "MASTER_DASHBOARD.html").write_text(html, encoding="utf-8")

print(f"collected {len(all_rows)} model-rows across {sum(1 for s in summary if 'n' in s)} scored rounds")
print(f"  deliverable/all_scores.csv, all_scores.json, round_summary.csv")
print(f"  MASTER_DASHBOARD.html  (links {len(galleries)} galleries + paper + report + {len(bundles)} bundles)")
