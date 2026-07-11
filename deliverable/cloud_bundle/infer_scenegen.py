"""infer_scenegen.py — batch single-image->3D with SceneGen (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo README; see manuals/SCENEGEN.md).

Licence: MIT code (Mengmouxu/SceneGen) + MIT weights (haoningwu/SceneGen) — BUT the pipeline's
checkpoint recipe pulls facebook/VGGT-1B (CC-BY-NC-4.0): RESEARCH BENCHMARK ONLY until the
VGGT dependency question is settled on the pod (manual, licence section).
Runs inside the `scenegen` venv created by install_models.sh.

  python infer_scenegen.py manifest.json out/scenegen [masks_dir]

Writes out/scenegen/<key>.glb per manifest item. One failure never aborts the batch.
Masks: SceneGen REQUIRES per-object masks — uses masks/<key>.png (precompute_masks.py, rembg,
the SAM3D convention); falls back to an on-the-fly rembg mask if the file is missing.
Single-object protocol: image=[object], mask_image=[mask], scene_image=the full photo.
"""
import sys, os, json, time, inspect, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
masks_dir = sys.argv[3] if len(sys.argv) > 3 else "masks"
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/SceneGen"

# TRELLIS-family env pins BEFORE any pipeline import (TRELLIS lessons; manual issues #2-#4)
os.environ.setdefault("SPCONV_ALGO", "native")
os.environ.setdefault("ATTN_BACKEND", "sdpa")     # flash-attn ABI gotcha #6; flip on pod if flash-attn works
sys.path.insert(0, REPO)

from PIL import Image
import torch

# --- mask fallback (precomputed masks/<key>.png wins — same convention as infer_sam3d.py) -----
try:
    from rembg import remove, new_session
    _rembg = new_session("u2net")
    def fallback_mask(pil):
        a = remove(pil.convert("RGB"), session=_rembg).split()[-1]
        return a.point(lambda v: 255 if v > 40 else 0).convert("L")
except Exception:
    def fallback_mask(pil):
        return Image.new("L", pil.size, 255)       # last resort: full-frame mask

def load_mask(img, key):
    mp = os.path.join(BUNDLE, masks_dir, key + ".png")
    if os.path.exists(mp):
        return Image.open(mp).convert("L").resize(img.size)
    return fallback_mask(img)

# --- load pipeline ONCE (absolute checkpoint path — manual issue #4) --------------------------
print("[scenegen] loading checkpoints/scenegen (haoningwu/SceneGen) ...", flush=True)
from scenegen.pipelines import SceneGenImageToScenePipeline   # DRAFT: module path unverified — check repo layout on pod
pipe = SceneGenImageToScenePipeline.from_pretrained(os.path.join(REPO, "checkpoints/scenegen"))
if hasattr(pipe, "cuda"):
    pipe.cuda()
SEED_KW = "seed" in inspect.signature(pipe.run_scene).parameters   # repo's own script sets no seed
SAMPLER = {"steps": 25, "cfg_strength": 5.0, "cfg_interval": [0.5, 1.0], "rescale_t": 3.0}
print(f"[scenegen] loaded. {len(items)} inputs. per-call seed kwarg: {SEED_KW}", flush=True)

ok = 0
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        ok += 1
        print(f"[scenegen] skip {key} (exists)", flush=True); continue
    img_path = it["input"] if os.path.isabs(it["input"]) else os.path.join(BUNDLE, it["input"])
    t0 = time.time()
    try:
        # deterministic: seed 42, same contract as every other engine in the bundle
        torch.manual_seed(42)
        img = Image.open(img_path).convert("RGB")
        mask = load_mask(img, key)
        kw = dict(image=[img], mask_image=[mask], scene_image=img, preprocess_image=True,
                  sparse_structure_sampler_params=dict(SAMPLER),
                  slat_sampler_params=dict(SAMPLER),
                  resorted_indices=[0])            # single object — identity order
        if SEED_KW:
            kw["seed"] = 42
        outputs = pipe.run_scene(**kw)
        outputs["scene"].export(out)               # textured GLB (repo inference.py does the same)
        ok += 1
        print(f"[scenegen] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[scenegen] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print(f"[scenegen] batch done: {ok}/{len(items)}", flush=True)
