"""make_variant_menu.py — the 8-way TripoSG improvement menu (user-pickable).

For 8 representative items, process the RAW TripoSG mesh through 8 candidate
pipelines and write results/<list>/<cat>/triposg_v{1..8}.glb. The visualizer
picks them up as candidates; the user's "Select this one" votes choose the
default ingestion profile for the whole catalog.

  v1 repair packs only (today's catalog profile — the baseline)
  v2 repair + Taubin smoothing        (feature-preserving de-bumping)
  v3 repair + Laplacian smoothing     (stronger, softer look)
  v4 repair + Humphrey filter         (volume-preserving smoothing)
  v5 repair + lean decimation (~5k)   (BIM-lean geometry)
  v6 repair + photo colour tint       (dominant colour from the source photo)
  v7 repair + Taubin + tint           (smooth AND coloured)
  v8 repair + Humphrey + tint + lean  (the all-in profile)

    python make_variant_menu.py
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import trimesh
from trimesh import smoothing
from PIL import Image

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend" / "python-scripts"))
from repair_packs import repair_mesh

RES = HERE / "results"
IMG = HERE / "images"
SAMPLES = [("list05", c) for c in
           ("office_chair", "desk", "table", "sofa", "bookshelf", "lamp", "cabinet", "stool")]


def photo_tint(cat: str, lst: str):
    """Dominant saturated colour of the photo's centre — NOT the mean (mean of any
    real photo converges to muddy gray; learned from v6's [117,117,110])."""
    import colorsys
    for ext in (".jpg", ".png"):
        p = IMG / cat / f"{lst}{ext}"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        w, h = im.size
        crop = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4)).resize((96, 96))
        q = crop.quantize(colors=8)
        counts = sorted(q.getcolors(), reverse=True)          # [(count, palette_idx)]
        pal = q.getpalette()
        best, best_score = None, -1.0
        for count, idx in counts:
            r, g, b = pal[3 * idx: 3 * idx + 3]
            hsv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            sat, val = hsv[1], hsv[2]
            score = count * (0.35 + sat) * (0.5 if val < 0.08 or val > 0.97 else 1.0)
            if score > best_score:
                best_score, best = score, (r, g, b)
        if best:
            return np.array([*best, 255], dtype=np.uint8)
    return None


def tinted(mesh: trimesh.Trimesh, rgba) -> trimesh.Trimesh:
    m = mesh.copy()
    if rgba is not None:
        m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=np.tile(rgba, (len(m.vertices), 1)))
    return m


def lean(mesh: trimesh.Trimesh, target=5000) -> trimesh.Trimesh:
    if len(mesh.faces) <= target:
        return mesh
    try:
        return mesh.simplify_quadric_decimation(face_count=target)
    except BaseException:
        return mesh


made = 0
for lst, cat in SAMPLES:
    src = RES / lst / cat / "triposg.glb"
    if not src.exists():
        print(f"[menu] missing {src}, skipped")
        continue
    raw = trimesh.load(src, force="mesh")
    base, _ = repair_mesh(raw.copy(), label=cat, category=cat)
    rgba = photo_tint(cat, lst)

    taub = base.copy(); smoothing.filter_taubin(taub, lamb=0.5, nu=-0.53, iterations=10)
    lap = base.copy();  smoothing.filter_laplacian(lap, iterations=5)
    hum = base.copy();  smoothing.filter_humphrey(hum, iterations=10)

    variants = {
        "triposg_v1": base,
        "triposg_v2": taub,
        "triposg_v3": lap,
        "triposg_v4": hum,
        "triposg_v5": lean(base.copy()),
        "triposg_v6": tinted(base, rgba),
        "triposg_v7": tinted(taub, rgba),
        "triposg_v8": tinted(lean(hum.copy()), rgba),
    }
    for key, m in variants.items():
        m.export(RES / lst / cat / f"{key}.glb")
        made += 1
    print(f"[menu] {lst}/{cat}: 8 variants", flush=True)
print(f"[menu] done: {made} variant meshes")
