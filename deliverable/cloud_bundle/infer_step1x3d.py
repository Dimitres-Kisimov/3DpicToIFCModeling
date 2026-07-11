"""infer_step1x3d.py — batch single-image->3D with Step1X-3D (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo README; see manuals/STEP1X_3D.md).

Licence: Apache-2.0 code + Apache-2.0 weights (stepfun-ai/Step1X-3D) — royalty-free, EU-safe.
Runs inside the `step1x3d` venv created by install_models.sh.

  python infer_step1x3d.py manifest.json out/step1x3d

Writes out/step1x3d/<key>.glb per manifest item. One failure never aborts the batch.
Geometry stage only by default (that's what eval_accuracy.py scores); export STEP1X_TEXTURE=1
to also run the texture-synthesis stage (adds ~27 GB VRAM total + the nvdiffrast dep).
"""
import sys, os, json, time, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
sys.path.insert(0, "/workspace/repos/Step1X-3D")

import torch
from PIL import Image

WANT_TEXTURE = os.environ.get("STEP1X_TEXTURE", "0") == "1"

# --- load geometry pipeline ONCE ------------------------------------------------
print("[step1x3d] loading stepfun-ai/Step1X-3D (Step1X-3D-Geometry-1300m) ...", flush=True)
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
geo_pipe = Step1X3DGeometryPipeline.from_pretrained(
    "stepfun-ai/Step1X-3D", subfolder="Step1X-3D-Geometry-1300m").to("cuda")

tex_pipe = None
if WANT_TEXTURE:
    try:
        from step1x3d_texture.pipelines.step1x_3d_texture_synthesis_pipeline import Step1X3DTexturePipeline
        tex_pipe = Step1X3DTexturePipeline.from_pretrained("stepfun-ai/Step1X-3D", subfolder="Step1X-3D-Texture")
        print("[step1x3d] texture stage loaded.", flush=True)
    except Exception as e:
        print(f"[step1x3d] texture stage unavailable ({e!r}) — geometry-only", flush=True)
print(f"[step1x3d] loaded. {len(items)} inputs.", flush=True)

def generate(img_path):
    """Geometry stage with the seed-42 contract; generator kwarg is diffusers-style but
    unverified for this pipeline (draft) — fall back to a global seed if rejected."""
    try:
        gen = torch.Generator(device="cuda").manual_seed(42)
        return geo_pipe(img_path, generator=gen, guidance_scale=7.5, num_inference_steps=50)
    except TypeError:
        torch.manual_seed(42)
        return geo_pipe(img_path, guidance_scale=7.5, num_inference_steps=50)

for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[step1x3d] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img_path = os.path.join(BUNDLE, it["input"])
        res = generate(img_path)
        mesh = res.mesh[0]                              # README: out.mesh[0].export("untexture_mesh.glb")
        if tex_pipe is not None:
            try:
                mesh = tex_pipe(img_path, mesh)         # textured trimesh per README
            except Exception as te:
                print(f"[step1x3d] texture FAIL {key} ({te!r}) — exporting untextured", flush=True)
        mesh.export(out)
        print(f"[step1x3d] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[step1x3d] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[step1x3d] batch done.", flush=True)
