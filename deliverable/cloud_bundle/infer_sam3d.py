"""infer_sam3d.py — batch single-image->3D with Meta SAM 3D Objects.

REWRITTEN 2026-07-11 from the pod-proven recipe in deliverable/manuals/SAM3D.md:
sdpa attention pin, numpy image+mask (not PIL), Inference API loaded ONCE,
utils3d viz shim, out['mesh'] list unwrap. Never writes placeholders — an item
either produces its own mesh or is logged FAIL and skipped (the previous version
copied a repo asset on failure, which fabricated 180 identical outputs).

Masks: uses masks/<key>.png (precompute_masks.py, rembg) when present — required
for internet photos; falls back to the white-background heuristic that works for
catalog product shots.

  python infer_sam3d.py manifest.json out/sam3d [masks_dir]
"""
import sys, os, json, time, glob, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
masks_dir = sys.argv[3] if len(sys.argv) > 3 else "masks"
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/SAM3D"

# --- env pins BEFORE any sam3d import (manual fixes #2, #4, #5) ---
os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")
os.environ.setdefault("LIDRA_SKIP_INIT", "true")
os.environ["SPARSE_ATTN_BACKEND"] = "sdpa"
os.environ["ATTN_BACKEND"] = "sdpa"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "notebook"))

# --- utils3d shim (manual fix #9): SAM3D imports viz helpers newer utils3d dropped ---
try:
    import utils3d.numpy as _u3n
    for _fn in ("depth_edge", "normals_edge", "points_to_normals", "image_uv", "image_mesh"):
        if not hasattr(_u3n, _fn):
            setattr(_u3n, _fn, (lambda *a, **k: None))
except Exception:
    pass

import numpy as np
from PIL import Image
import trimesh

from huggingface_hub import snapshot_download
snap = snapshot_download("facebook/sam-3d-objects")
yamls = glob.glob(os.path.join(snap, "**", "pipeline.yaml"), recursive=True)
assert yamls, f"pipeline.yaml not found under {snap}"
from inference import Inference          # notebook/inference.py (manual: real entrypoint)
inf = Inference(yamls[0], compile=False)
print(f"[sam3d] model loaded from {yamls[0]}", flush=True)


def load_image_and_mask(img_path, key):
    """RGB numpy + 0/1 numpy mask. Precomputed rembg mask wins; else white-bg heuristic."""
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    mp = os.path.join(BUNDLE, masks_dir, key + ".png")
    if os.path.exists(mp):
        m = np.array(Image.open(mp).convert("L").resize(img.size))
        return arr, (m > 127).astype(np.uint8)
    fg = (np.abs(arr.astype(int) - 255).sum(2) > 30).astype(np.uint8)
    return arr, fg


ok = 0
for it in items:
    key = it["key"]
    out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        ok += 1
        continue
    img_path = it["input"] if os.path.isabs(it["input"]) else os.path.join(BUNDLE, it["input"])
    t0 = time.time()
    try:
        arr, fg = load_image_and_mask(img_path, key)
        if fg.sum() < 100:
            raise ValueError("empty foreground mask")
        res = inf(arr, fg, seed=42)
        glb = res.get("glb") if isinstance(res, dict) else None
        if isinstance(glb, trimesh.Trimesh):
            glb.export(out)
        else:
            m = res["mesh"][0]            # LIST (batch dim) — manual fix #11
            trimesh.Trimesh(m.vertices.detach().cpu().numpy(),
                            m.faces.detach().cpu().numpy()).export(out)
        ok += 1
        print(f"[sam3d] OK {key} {time.time()-t0:.1f}s", flush=True)
    except Exception as e:
        print(f"[sam3d] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print(f"[sam3d] batch done: {ok}/{len(items)}", flush=True)
