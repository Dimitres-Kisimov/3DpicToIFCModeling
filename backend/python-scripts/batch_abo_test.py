"""
Batch A/B test: for N ABO models per furniture type, run the SAME asset screenshot
through TripoSR(SAM2) and TripoSR(rembg), keep the real ABO mesh, and render posters.
Loads the TripoSR model ONCE for speed. Writes everything to outputs/abo_test/ plus a
results.json the gallery builder consumes.

Usage: python batch_abo_test.py [types...] [--n 5]
"""
from __future__ import annotations
import os, sys, json, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "backend" / "triposr"))
os.environ["SCS_TRIPOSR_SKIP_POSTPROC"] = "0"   # full clean-up (debris filter + smooth)

ABO = REPO / "data" / "mesh_library_abo"

def _opt(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default

OUT = REPO / "outputs" / (_opt("--out") or "abo_test")
OUT.mkdir(parents=True, exist_ok=True)

import numpy as np
import torch
import trimesh
from PIL import Image
from tsr.system import TSR
from tsr.utils import resize_foreground

import run_triposr as rt
from _triposr_postprocess import clean_triposr_mesh
import render_glb_preview as rp


def log(m): print(f"[batch] {m}", flush=True)

# ---- pick types x N models from the manifest --------------------------------
import random
# positional args = types; everything after a --flag (and the flag) is excluded
_FLAGS = {"--n", "--out", "--seed"}
TYPES, skip = [], False
for a in sys.argv[1:]:
    if skip:
        skip = False; continue
    if a in _FLAGS:
        skip = True; continue
    if a == "--random":
        continue
    TYPES.append(a)
TYPES = TYPES or ["office_chair", "desk", "table", "sofa", "bookshelf"]
N = int(_opt("--n", 5))
RANDOM = "--random" in sys.argv
SEED = int(_opt("--seed", 0))

manifest = json.loads((ABO / "manifest.json").read_text(encoding="utf-8"))
by_cat = {}
for e in manifest:
    by_cat.setdefault(e.get("category"), []).append(e)

rng = random.Random(SEED)
jobs = []
for t in TYPES:
    pool = by_cat.get(t, [])
    picked = rng.sample(pool, min(N, len(pool))) if RANDOM else pool[:N]
    for e in picked:
        jobs.append((t, e))
log(f"types={TYPES} N={N} sampling={'RANDOM seed='+str(SEED) if RANDOM else 'first-N'} "
    f"out={OUT.name} -> {len(jobs)} models, {len(jobs)*2} TripoSR runs")

# ---- load TripoSR once -------------------------------------------------------
log("loading TripoSR model (once)...")
device = "cuda" if torch.cuda.is_available() else "cpu"
model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
model.renderer.set_chunk_size(8192 if device == "cuda" else 2048)
model.to(device)
log(f"model ready on {device}")


def reconstruct(image_path, out_glb, segmenter):
    os.environ["SCS_TRIPOSR_SEGMENTER"] = segmenter
    img_rgba = rt._segment_foreground(str(image_path))
    img_rgba = resize_foreground(img_rgba, 0.85)
    arr = np.array(img_rgba).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    image = Image.fromarray((arr * 255.0).astype(np.uint8))
    with torch.no_grad():
        codes = model([image], device=device)
    mesh = model.extract_mesh(codes, True, resolution=256 if device == "cuda" else 96)[0]
    mesh = clean_triposr_mesh(mesh)
    mesh.export(str(out_glb))
    if device == "cuda":
        torch.cuda.empty_cache()
    return len(mesh.faces)


INPUT_MODE = _opt("--input", "preview")   # 'preview' (clean render) | 'thumb' (real product photo)


def input_image_for(e):
    """Input image for reconstruction. 'thumb' = ABO real product photo (kills the
    self-referential bias); 'preview' = clean studio render; else render the mesh."""
    stem = Path(e["glb"]).stem
    if INPUT_MODE == "thumb":
        th = ABO / f"{stem}.thumb.png"
        if th.exists():
            return th
    prev = ABO / f"{stem}.preview.png"
    if prev.exists():
        return prev
    dst = OUT / f"{stem}.input.png"
    rp.render(str(ABO / e["glb"]), str(dst), az=-50, el=18)
    return dst


results = []
for i, (t, e) in enumerate(jobs, 1):
    sid = e.get("source_id") or Path(e["glb"]).stem
    base = f"{t}_{i:02d}"
    log(f"[{i}/{len(jobs)}] {t} / {sid}")
    try:
        inp = input_image_for(e)
        # copy input + ABO mesh
        shutil.copy(inp, OUT / f"{base}_input.png")
        shutil.copy(ABO / e["glb"], OUT / f"{base}_abo.glb")
        rp.render(str(ABO / e["glb"]), str(OUT / f"{base}_abo.png"), az=-50, el=18)
        # two reconstructions
        f_sam = reconstruct(inp, OUT / f"{base}_sam2.glb", "sam2")
        rp.render(str(OUT / f"{base}_sam2.glb"), str(OUT / f"{base}_sam2.png"), az=-50, el=18)
        f_rem = reconstruct(inp, OUT / f"{base}_rembg.glb", "rembg")
        rp.render(str(OUT / f"{base}_rembg.glb"), str(OUT / f"{base}_rembg.png"), az=-50, el=18)
        results.append({"type": t, "base": base, "source_id": sid,
                        "faces_sam2": f_sam, "faces_rembg": f_rem,
                        "abo_glb": e["glb"]})
        log(f"   ok: sam2={f_sam}f rembg={f_rem}f")
    except Exception as exc:
        import traceback; traceback.print_exc()
        log(f"   FAILED: {exc}")

(OUT / "results.json").write_text(json.dumps({"types": TYPES, "n": N, "results": results}, indent=2),
                                  encoding="utf-8")
log(f"DONE: {len(results)}/{len(jobs)} models -> {OUT/'results.json'}")
