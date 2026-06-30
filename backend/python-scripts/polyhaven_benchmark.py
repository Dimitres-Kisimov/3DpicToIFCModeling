"""
Round 3 (GSO substitute): benchmark TripoSR(SAM2) vs TripoSR(rembg) vs ground-truth mesh
on the Poly Haven CC0 (public-domain) model library — a DIFFERENT, commercial-safe dataset.

Downloads furniture models from the Poly Haven API, converts glTF->GLB, renders a clean input
per model, reconstructs with both segmenters, and writes outputs/abo_test_polyhaven/ in the same
format as the ABO rounds so score_abo_test.py / build_abo_gallery.py / export_abo_gallery.py work.

Usage: python polyhaven_benchmark.py [--per 4]
"""
from __future__ import annotations
import os, sys, json, shutil, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO / "backend" / "triposr"))
os.environ["SCS_TRIPOSR_SKIP_POSTPROC"] = "0"

CACHE = REPO / "data" / "mesh_library_polyhaven"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = REPO / "outputs" / "abo_test_polyhaven"; OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SCS-research/1.0"}
PER = int(sys.argv[sys.argv.index("--per") + 1]) if "--per" in sys.argv else 4

import numpy as np, torch, trimesh
from PIL import Image
from tsr.system import TSR
from tsr.utils import resize_foreground
import run_triposr as rt
from _triposr_postprocess import clean_triposr_mesh
import render_glb_preview as rp


def log(m): print(f"[ph] {m}", flush=True)
def get(url): return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
def dl(url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    with get(url) as r, open(dst, "wb") as f: f.write(r.read())


def classify(name):
    # Match on the model NAME only (Poly Haven names are descriptive: "ArmChair_01").
    # Using tags/categories caused false hits (e.g. a "bedroom" tag matching "bed").
    s = name.lower()
    for key, t in [("nightstand", "cabinet"), ("commode", "cabinet"), ("cabinet", "cabinet"),
                   ("dresser", "cabinet"), ("console", "cabinet"),
                   ("coffeetable", "table"), ("table", "table"), ("desk", "table"),
                   ("armchair", "chair"), ("rockingchair", "chair"), ("chair", "chair"),
                   ("ottoman", "sofa"), ("sofa", "sofa"), ("couch", "sofa"),
                   ("bed", "bed"), ("shelf", "bookshelf"), ("bookcase", "bookshelf"),
                   ("stool", "stool")]:
        if key in s:
            return t
    return None


# ---- pick furniture models --------------------------------------------------
log("fetching Poly Haven model list...")
assets = json.load(get("https://api.polyhaven.com/assets?type=models"))
buckets = {}
for aid, meta in assets.items():
    t = classify(aid)
    if t:
        buckets.setdefault(t, []).append(aid)
picks = []
for t, ids in sorted(buckets.items()):
    for aid in sorted(ids)[:PER]:
        picks.append((t, aid))
log(f"selected {len(picks)} models across {len(buckets)} types: "
    + ", ".join(f"{t}:{len([1 for tt,_ in picks if tt==t])}" for t in sorted(buckets)))


def fetch_glb(aid):
    """Download + convert a Poly Haven model to a single cached GLB."""
    glb = CACHE / f"{aid}.glb"
    if glb.exists():
        return glb
    files = json.load(get(f"https://api.polyhaven.com/files/{aid}"))
    # choose lowest available gltf resolution for speed
    res = sorted(files["gltf"].keys())[0]
    node = files["gltf"][res]["gltf"]
    tmp = CACHE / "_tmp" / aid
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    dl(node["url"], tmp / f"{aid}.gltf")
    for rel, m in node.get("include", {}).items():
        if rel.endswith(".bin"):
            dl(m["url"], tmp / rel.replace("/", os.sep))
    mesh = trimesh.load(tmp / f"{aid}.gltf", force="mesh", skip_materials=True)
    mesh.export(glb)
    shutil.rmtree(tmp)
    return glb


# ---- load TripoSR once -------------------------------------------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
log(f"loading TripoSR (once) on {device}...")
model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
model.renderer.set_chunk_size(8192 if device == "cuda" else 2048); model.to(device)


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
for i, (t, aid) in enumerate(picks, 1):
    base = f"{t}_{i:02d}"
    log(f"[{i}/{len(picks)}] {t} / {aid}")
    try:
        gt = fetch_glb(aid)
        inp = OUT / f"{base}_input.png"
        rp.render(str(gt), str(inp), az=-50, el=18)            # clean render = input
        shutil.copy(gt, OUT / f"{base}_abo.glb")               # GT mesh (keep _abo suffix for tooling)
        rp.render(str(gt), str(OUT / f"{base}_abo.png"), az=-50, el=18)
        fs = reconstruct(inp, OUT / f"{base}_sam2.glb", "sam2")
        rp.render(str(OUT / f"{base}_sam2.glb"), str(OUT / f"{base}_sam2.png"), az=-50, el=18)
        fr = reconstruct(inp, OUT / f"{base}_rembg.glb", "rembg")
        rp.render(str(OUT / f"{base}_rembg.glb"), str(OUT / f"{base}_rembg.png"), az=-50, el=18)
        results.append({"type": t, "base": base, "source_id": aid,
                        "faces_sam2": fs, "faces_rembg": fr, "abo_glb": f"{aid}.glb"})
        log(f"   ok sam2={fs} rembg={fr}")
    except Exception as e:
        import traceback; traceback.print_exc(); log(f"   FAILED {e}")

(OUT / "results.json").write_text(json.dumps(
    {"dataset": "polyhaven-cc0", "types": sorted(buckets), "results": results}, indent=2), encoding="utf-8")
log(f"DONE {len(results)}/{len(picks)} -> {OUT/'results.json'}")
