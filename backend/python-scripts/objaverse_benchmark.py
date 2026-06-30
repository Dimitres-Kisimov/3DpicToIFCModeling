"""
Round 4: benchmark TripoSR(SAM2) vs TripoSR(rembg) vs ground-truth mesh on an Objaverse
furniture subset (LVIS-annotated). RESEARCH / INTERNAL BENCHMARKING ONLY -- Objaverse objects
carry per-object (often non-commercial / research) licenses and MUST NOT be shipped in the product;
they are used here solely to measure reconstruction fidelity. Each object's license is recorded.

Writes outputs/abo_test_objaverse/ in the same format as the other rounds.
Usage: python objaverse_benchmark.py [--per 4] [--seed 42]
"""
from __future__ import annotations
import os, sys, json, shutil, random
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "backend" / "triposr"))
os.environ["SCS_TRIPOSR_SKIP_POSTPROC"] = "0"
OUT = REPO / "outputs" / "abo_test_objaverse"; OUT.mkdir(parents=True, exist_ok=True)
PER = int(sys.argv[sys.argv.index("--per") + 1]) if "--per" in sys.argv else 4
SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 42

import numpy as np, torch, trimesh
from PIL import Image
import objaverse
from tsr.system import TSR
from tsr.utils import resize_foreground
import run_triposr as rt
from _triposr_postprocess import clean_triposr_mesh
import render_glb_preview as rp


def log(m): print(f"[obj] {m}", flush=True)

# LVIS category -> our benchmark type (aligned with the ABO/Poly Haven rounds)
CATMAP = {
    "chair": "chair", "armchair": "chair", "rocking_chair": "chair",
    "table": "table", "coffee_table": "table", "dining_table": "table",
    "sofa": "sofa", "loveseat": "sofa",
    "stool": "stool", "footstool": "stool", "ottoman": "stool",
    "bookcase": "bookshelf",
    "cabinet": "cabinet", "dresser": "cabinet", "wardrobe": "cabinet",
    "lamp": "lamp", "bed": "bed",
}

log("loading LVIS annotations...")
lvis = objaverse.load_lvis_annotations()
by_type = {}
for cat, uids in lvis.items():
    t = CATMAP.get(cat)
    if t:
        by_type.setdefault(t, []).extend(uids)

rng = random.Random(SEED)
picks = []
for t in sorted(by_type):
    pool = sorted(set(by_type[t]))
    for uid in rng.sample(pool, min(PER, len(pool))):
        picks.append((t, uid))
log(f"selected {len(picks)} objects across {len(by_type)} types (seed {SEED})")

# licenses (bulk metadata; tolerate failure) + per-object downloads with retry
uids = [u for _, u in picks]
try:
    anns = objaverse.load_annotations(uids)
except Exception as _e:
    log(f"annotations fetch failed ({_e}); licenses -> unknown"); anns = {}


def fetch_object(uid, retries=4):
    """Download one Objaverse GLB; retry on transient network errors. None on failure."""
    for k in range(retries):
        try:
            p = objaverse.load_objects([uid], download_processes=1)
            if p.get(uid) and os.path.exists(p[uid]):
                return p[uid]
        except Exception as e:
            log(f"   retry {k + 1}/{retries} for {uid[:8]}: {type(e).__name__}")
    return None

device = "cuda" if torch.cuda.is_available() else "cpu"
log(f"loading TripoSR (once) on {device}...")
model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
model.renderer.set_chunk_size(8192 if device == "cuda" else 2048); model.to(device)


def normalize_glb(src, dst):
    """Load (possibly multi-mesh) Objaverse GLB, keep geometry, re-export single GLB."""
    m = trimesh.load(src, force="mesh", skip_materials=True)
    if m.vertices.shape[0] == 0:
        raise ValueError("empty mesh")
    m.export(dst)
    return len(m.faces)


def reconstruct(image_path, out_glb, segmenter):
    os.environ["SCS_TRIPOSR_SEGMENTER"] = segmenter
    rgba = rt._segment_foreground(str(image_path))
    rgba = resize_foreground(rgba, 0.85)
    a = np.array(rgba).astype(np.float32) / 255.0
    a = a[:, :, :3] * a[:, :, 3:4] + (1 - a[:, :, 3:4]) * 0.5
    img = Image.fromarray((a * 255).astype(np.uint8))
    with torch.no_grad():
        codes = model([img], device=device)
    mesh = clean_triposr_mesh(model.extract_mesh(codes, True, resolution=256 if device == "cuda" else 96)[0])
    mesh.export(str(out_glb))
    if device == "cuda": torch.cuda.empty_cache()
    return len(mesh.faces)


results = []
for i, (t, uid) in enumerate(picks, 1):
    base = f"{t}_{i:02d}"
    lic = (anns.get(uid, {}) or {}).get("license", "unknown")
    log(f"[{i}/{len(picks)}] {t} / {uid[:8]} (license={lic})")
    try:
        src = fetch_object(uid)
        if not src or not os.path.exists(src):
            log("   download failed after retries; skip"); continue
        gt = OUT / f"{base}_abo.glb"
        gf = normalize_glb(src, gt)
        inp = OUT / f"{base}_input.png"; rp.render(str(gt), str(inp), az=-50, el=18)
        rp.render(str(gt), str(OUT / f"{base}_abo.png"), az=-50, el=18)
        fs = reconstruct(inp, OUT / f"{base}_sam2.glb", "sam2")
        rp.render(str(OUT / f"{base}_sam2.glb"), str(OUT / f"{base}_sam2.png"), az=-50, el=18)
        fr = reconstruct(inp, OUT / f"{base}_rembg.glb", "rembg")
        rp.render(str(OUT / f"{base}_rembg.glb"), str(OUT / f"{base}_rembg.png"), az=-50, el=18)
        results.append({"type": t, "base": base, "source_id": uid, "license": lic,
                        "gt_faces": gf, "faces_sam2": fs, "faces_rembg": fr})
        log(f"   ok sam2={fs} rembg={fr}")
    except Exception as e:
        import traceback; traceback.print_exc(); log(f"   FAILED {e}")

(OUT / "results.json").write_text(json.dumps(
    {"dataset": "objaverse-lvis (RESEARCH/INTERNAL ONLY)", "types": sorted(by_type),
     "results": results}, indent=2), encoding="utf-8")
log(f"DONE {len(results)}/{len(picks)} -> {OUT/'results.json'}")
