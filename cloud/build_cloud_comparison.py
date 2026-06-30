"""build_cloud_comparison.py — score cloud-generated meshes vs ABO ground truth (the SAME
eval_accuracy metric as TripoSR) and build the front-facing spinning comparison gallery + stills.
Run LOCALLY after pulling cloud GLBs into deliverable/cloud_results/<model>/<key>.glb.

Produces deliverable/cloud_gallery/:
  index.html          interactive: each row = Input | TripoSR-SAM2 | TripoSR-rembg | <cloud models> | ABO GT
                      (draggable, auto-rotating, front-facing model-viewers, F-score under each)
  gallery_static.html offline image-only version (rendered stills) for the PDF
  assets/             every input PNG, every model GLB, every rendered still
  cloud_scores.csv    per (item, model) chamfer + F-score
"""
import sys, os, json, io, csv, shutil
from pathlib import Path
import numpy as np
from PIL import Image
import trimesh

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
from eval_accuracy import evaluate, load_mesh

MAN = json.loads((REPO / "deliverable" / "local_scoring_manifest.json").read_text(encoding="utf-8"))
BUNDLE = REPO / "deliverable" / "cloud_bundle"
CLOUD = REPO / "deliverable" / "cloud_results"
OUT = REPO / "deliverable" / "cloud_gallery"
ASSETS = OUT / "assets"
if ASSETS.exists():
    shutil.rmtree(ASSETS)
ASSETS.mkdir(parents=True, exist_ok=True)

cloud_models = sorted(d.name for d in CLOUD.iterdir() if d.is_dir()) if CLOUD.exists() else []
# column order: TripoSR variants, then cloud models, then ground truth
MODEL_ORDER = ["triposr_sam2", "triposr_rembg"] + cloud_models + ["abo_gt"]
LABELS = {"triposr_sam2": "TripoSR·SAM2", "triposr_rembg": "TripoSR·rembg",
          "triposg": "TripoSG", "trellis": "TRELLIS", "trellis2": "TRELLIS.2",
          "instantmesh": "InstantMesh", "sam3d": "SAM 3D", "abo_gt": "ABO mesh (truth)"}
print("models in gallery:", MODEL_ORDER)


def render_still(glb_path, out_png, size=512):
    try:
        m = trimesh.load(str(glb_path), force="mesh")
        png = m.scene().save_image(resolution=(size, size))
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        comp = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img).convert("RGB")
        comp.save(out_png)
    except Exception as e:
        Image.new("RGB", (size, size), (40, 40, 40)).save(out_png)


rows, items = [], []
for it in MAN:
    key, gt, t = it["key"], it["gt"], it["type"]
    inp = BUNDLE / "inputs" / f"{key}.png"
    if inp.exists():
        shutil.copy(inp, ASSETS / f"{key}_input.png")
    glbs = {"triposr_sam2": it.get("triposr_sam2_glb"),
            "triposr_rembg": it.get("triposr_rembg_glb"), "abo_gt": gt}
    for cm in cloud_models:
        g = CLOUD / cm / f"{key}.glb"
        if g.exists():
            glbs[cm] = str(g)
    scores = {}
    for m in MODEL_ORDER:
        gp = glbs.get(m)
        if not gp or not Path(gp).exists():
            continue
        shutil.copy(gp, ASSETS / f"{key}_{m}.glb")
        render_still(ASSETS / f"{key}_{m}.glb", ASSETS / f"{key}_{m}.png")
        if m == "abo_gt":
            scores[m] = 1.0
        else:
            try:
                r = evaluate(load_mesh(gt), load_mesh(gp), n=30000, tau=0.02)
                scores[m] = r["fscore"]
                rows.append({"key": key, "type": t, "model": m,
                             "fscore": r["fscore"], "chamfer": r["chamfer"]})
            except Exception as e:
                scores[m] = None
                print(f"  score FAIL {m}/{key}: {e}")
    items.append({"key": key, "type": t, "scores": scores})
    print(f"  {key}: " + "  ".join(f"{m}={scores.get(m)}" for m in MODEL_ORDER if m in scores))

# ---- scores csv + per-model means -------------------------------------------
with open(OUT / "cloud_scores.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["key", "type", "model", "fscore", "chamfer"])
    w.writeheader(); w.writerows(rows)
means = {}
for m in MODEL_ORDER:
    fs = [r["fscore"] for r in rows if r["model"] == m]
    if fs:
        means[m] = sum(fs) / len(fs)

# ---- HTML --------------------------------------------------------------------
CSS = '''body{margin:0;background:#15171c;color:#e7e7ea;font-family:system-ui,sans-serif}
h1{padding:12px 16px;margin:0;border-bottom:1px solid #333}h1 small{color:#888;font-weight:400}
h2{padding:14px 16px 4px;margin:0;color:#cfd3da}
.sum{padding:8px 16px;color:#bbb;font-size:13px;border-bottom:1px solid #2a2d34}
.model{display:grid;grid-template-columns:repeat(%d,1fr);gap:8px;padding:8px 16px;border-bottom:1px solid #2a2d34}
.cell{background:#23262d;border:1px solid #333;border-radius:8px;overflow:hidden;text-align:center}
.cell h4{margin:0;padding:7px 6px;font-size:12px;border-bottom:1px solid #333}
.win{color:#7ad28a}.gen{color:#d6b08a}.f{display:block;color:#9aa;font-size:11px;padding:3px}
img{width:100%%;height:210px;object-fit:contain;background:#fff;display:block}
model-viewer{width:100%%;height:210px;background:#23262d}''' % (len(MODEL_ORDER) + 1)


def cls(m):
    return "win" if m == "abo_gt" else "gen"


def panel(key, m, interactive):
    lab = LABELS.get(m, m)
    s = items_by_key[key]["scores"].get(m)
    fl = "F=1.00" if m == "abo_gt" else (f"F={s:.2f}" if isinstance(s, float) else "")
    glb, png = f"assets/{key}_{m}.glb", f"assets/{key}_{m}.png"
    if interactive and (ASSETS / f"{key}_{m}.glb").exists():
        body = (f'<model-viewer src="{glb}" poster="{png}" camera-controls auto-rotate '
                f'auto-rotate-delay="2000" rotation-per-second="20deg" camera-orbit="0deg 76deg 105%" '
                f'interaction-prompt="none"></model-viewer>')
    else:
        body = f'<img src="{png}">'
    return f'<div class="cell"><h4 class="{cls(m)}">{lab}</h4>{body}<span class="f">{fl}</span></div>'


items_by_key = {it["key"]: it for it in items}
by_type = {}
for it in items:
    by_type.setdefault(it["type"], []).append(it)


def build(interactive):
    out = []
    for t, its in by_type.items():
        out.append(f'<h2>{t.replace("_"," ").title()}</h2>')
        for it in its:
            k = it["key"]
            cells = [f'<div class="cell"><h4>Input (2D)</h4><img src="assets/{k}_input.png"></div>']
            cells += [panel(k, m, interactive) for m in MODEL_ORDER if m in it["scores"]]
            out.append(f'<div class="model">{"".join(cells)}</div>')
    return "\n".join(out)


sumline = " · ".join(f"{LABELS.get(m,m)} mean F={means[m]:.3f}" for m in MODEL_ORDER if m in means)
head = lambda mv: (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
    f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>SCS cloud 3D comparison</title>'
    + ('<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>' if mv else '')
    + f'<style>{CSS}</style></head><body>')
title = (f'<h1>Single-image → 3D: model comparison <small>{len(items)} furniture types · '
         f'same 2D input, same ABO ground truth, same metric · front-facing, drag to orbit</small></h1>'
         f'<div class="sum">Mean F-score@0.02 vs ground truth — {sumline}</div>')

(OUT / "index.html").write_text(head(True) + title + build(True) + "</body></html>", encoding="utf-8")
(OUT / "gallery_static.html").write_text(head(False) + title + build(False) + "</body></html>", encoding="utf-8")

print("\n=== mean F-score@0.02 vs ABO ground truth ===")
for m in MODEL_ORDER:
    if m in means:
        print(f"  {LABELS.get(m,m):20} {means[m]:.3f}")
print(f"\nwrote {OUT/'index.html'} (interactive) + gallery_static.html + cloud_scores.csv")
