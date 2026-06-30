"""build_cloud_comparison.py — score cloud meshes vs ABO ground truth (same eval_accuracy as
TripoSR) and build the INTERACTIVE spinning 3D gallery (model-viewer, one front-facing camera-orbit
for every model — like the TripoSR galleries). Run LOCALLY after pulling cloud GLBs into
deliverable/cloud_results/<model>/<key>.glb.

Robust by design: Phase 1 (scoring + GLB copy + interactive HTML + CSV) uses NO server-side rendering,
so it always completes. Phase 2 (optional static stills via trimesh) is best-effort and cannot break
Phase 1 — enable with SCS_RENDER_STILLS=1 (off by default; trimesh/pyglet is unstable on Windows).

Outputs deliverable/cloud_gallery/: index.html (interactive, spinning, front-facing) + cloud_scores.csv
(+ gallery_static.html if stills enabled).
"""
import sys, os, io, csv, shutil
from pathlib import Path
import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "python-scripts"))
from eval_accuracy import evaluate, load_mesh

MAN = __import__("json").loads((REPO / "deliverable" / "local_scoring_manifest.json").read_text(encoding="utf-8"))
BUNDLE = REPO / "deliverable" / "cloud_bundle"
CLOUD = REPO / "deliverable" / "cloud_results"
OUT = REPO / "deliverable" / "cloud_gallery"
ASSETS = OUT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
RENDER_STILLS = os.environ.get("SCS_RENDER_STILLS") == "1"

cloud_models = sorted(d.name for d in CLOUD.iterdir() if d.is_dir()) if CLOUD.exists() else []
MODEL_ORDER = ["triposr_sam2", "triposr_rembg"] + cloud_models + ["abo_gt"]
LABELS = {"triposr_sam2": "TripoSR·SAM2", "triposr_rembg": "TripoSR·rembg", "triposg": "TripoSG",
          "trellis": "TRELLIS", "trellis2": "TRELLIS.2", "instantmesh": "InstantMesh",
          "sam3d": "SAM 3D", "abo_gt": "ABO mesh (truth)"}
print("models in gallery:", MODEL_ORDER)

# ---- Phase 1: score + copy GLBs (NO rendering — always completes) ------------
rows, items = [], []
for it in MAN:
    key, gt, t = it["key"], it["gt"], it["type"]
    if (BUNDLE / "inputs" / f"{key}.png").exists():
        shutil.copy(BUNDLE / "inputs" / f"{key}.png", ASSETS / f"{key}_input.png")
    glbs = {"triposr_sam2": it.get("triposr_sam2_glb"),
            "triposr_rembg": it.get("triposr_rembg_glb"), "abo_gt": gt}
    for cm in cloud_models:
        g = CLOUD / cm / f"{key}.glb"
        if g.exists():
            glbs[cm] = str(g)
    scores, present = {}, []
    for m in MODEL_ORDER:
        gp = glbs.get(m)
        if not gp or not Path(gp).exists():
            continue
        shutil.copy(gp, ASSETS / f"{key}_{m}.glb")
        present.append(m)
        if m == "abo_gt":
            scores[m] = 1.0
        else:
            try:
                r = evaluate(load_mesh(gt), load_mesh(gp), n=30000, tau=0.02)
                scores[m] = r["fscore"]
                rows.append({"key": key, "type": t, "model": m, "fscore": r["fscore"], "chamfer": r["chamfer"]})
            except Exception as e:
                scores[m] = None
                print(f"  score FAIL {m}/{key}: {e}")
    items.append({"key": key, "type": t, "scores": scores, "present": present})
    print(f"  {key}: " + "  ".join(f"{m}={scores.get(m)}" for m in present))

with open(OUT / "cloud_scores.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["key", "type", "model", "fscore", "chamfer"]); w.writeheader(); w.writerows(rows)
means = {m: (lambda v: sum(v) / len(v))([r["fscore"] for r in rows if r["model"] == m])
         for m in MODEL_ORDER if any(r["model"] == m for r in rows)}

# ---- interactive gallery (model-viewer renders the GLB live; one front camera-orbit) ----
ncol = len(MODEL_ORDER) + 1
CSS = ('body{margin:0;background:#15171c;color:#e7e7ea;font-family:system-ui,sans-serif}'
       'h1{padding:12px 16px;margin:0;border-bottom:1px solid #333}h1 small{color:#888;font-weight:400}'
       'h2{padding:14px 16px 4px;margin:0;color:#cfd3da}.sum{padding:8px 16px;color:#bbb;font-size:13px;border-bottom:1px solid #2a2d34}'
       '.model{display:grid;grid-template-columns:repeat(%d,1fr);gap:8px;padding:8px 16px;border-bottom:1px solid #2a2d34}'
       '.cell{background:#23262d;border:1px solid #333;border-radius:8px;overflow:hidden;text-align:center}'
       '.cell h4{margin:0;padding:7px 6px;font-size:12px;border-bottom:1px solid #333}.win{color:#7ad28a}.gen{color:#d6b08a}'
       '.f{display:block;color:#9aa;font-size:11px;padding:3px}img{width:100%%;height:210px;object-fit:contain;background:#fff;display:block}'
       'model-viewer{width:100%%;height:210px;background:#fff}') % ncol
by_type = {}
for it in items:
    by_type.setdefault(it["type"], []).append(it)


def cell(it, m):
    k = it["key"]; lab = LABELS.get(m, m); s = it["scores"].get(m)
    fl = "F=1.00" if m == "abo_gt" else (f"F={s:.2f}" if isinstance(s, float) else "")
    cls = "win" if m == "abo_gt" else "gen"
    poster = f' poster="assets/{k}_input.png"'  # input as the loading placeholder
    mv = (f'<model-viewer src="assets/{k}_{m}.glb"{poster} camera-controls auto-rotate '
          f'auto-rotate-delay="1500" rotation-per-second="22deg" camera-orbit="0deg 76deg 105%" '
          f'interaction-prompt="none" shadow-intensity="0.6" exposure="1.1"></model-viewer>')
    return f'<div class="cell"><h4 class="{cls}">{lab}</h4>{mv}<span class="f">{fl}</span></div>'


rowsel = []
for t, its in by_type.items():
    rowsel.append(f'<h2>{t.replace("_"," ").title()}</h2>')
    for it in its:
        cells = [f'<div class="cell"><h4>Input (2D)</h4><img src="assets/{it["key"]}_input.png"></div>']
        cells += [cell(it, m) for m in MODEL_ORDER if m in it["present"]]
        rowsel.append(f'<div class="model">{"".join(cells)}</div>')
sumline = " · ".join(f"{LABELS.get(m,m)} F={means[m]:.3f}" for m in MODEL_ORDER if m in means)
html = ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>SCS single-image→3D — interactive comparison</title>'
        '<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>'
        f'<style>{CSS}</style></head><body>'
        f'<h1>Single-image → 3D: model comparison <small>{len(items)} furniture types · same 2D input, same '
        'ABO ground truth, same metric · every panel front-facing (camera-orbit 0/76), drag to orbit · auto-spins</small></h1>'
        f'<div class="sum">Mean F-score@0.02 vs ground truth — {sumline}</div>'
        + "\n".join(rowsel) + "</body></html>")
(OUT / "index.html").write_text(html, encoding="utf-8")

print("\n=== mean F-score@0.02 vs ABO ground truth ===")
for m in MODEL_ORDER:
    if m in means:
        print(f"  {LABELS.get(m,m):20} {means[m]:.3f}")
print(f"\nwrote {OUT/'index.html'} (interactive, spinning) + cloud_scores.csv")

# ---- Phase 2: optional static stills (best-effort; cannot affect Phase 1) ----
if RENDER_STILLS:
    print("rendering static stills (best-effort)...")
    from PIL import Image
    def render_still(glb, png, size=512):
        try:
            m = trimesh.load(str(glb), force="mesh"); im = Image.open(io.BytesIO(m.scene().save_image(resolution=(640, 640)))).convert("RGBA")
            comp = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im).convert("RGB")
            a = np.array(comp).astype(int); fg = np.abs(a - 255).sum(2) > 30; ys, xs = np.where(fg)
            if len(xs):
                c = comp.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
                side = max(1, int(max(c.size) / 0.7)); cv = Image.new("RGB", (side, side), (255, 255, 255))
                cv.paste(c, ((side - c.width) // 2, (side - c.height) // 2)); cv.resize((size, size)).save(png)
        except Exception as e:
            print(f"  still FAIL {glb}: {e}")
    for it in items:
        for m in it["present"]:
            render_still(ASSETS / f'{it["key"]}_{m}.glb', ASSETS / f'{it["key"]}_{m}.png')
    print("stills done.")
