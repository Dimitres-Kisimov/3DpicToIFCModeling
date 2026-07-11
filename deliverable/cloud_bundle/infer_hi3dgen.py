"""infer_hi3dgen.py — batch single-image->3D with Hi3DGen / Stable3DGen (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo's app.py; see manuals/HI3DGEN.md).

NAMING TRAP: the paper is "Hi3DGen" but the code repo is github.com/Stable-X/Stable3DGen
(Stable-X/Hi3DGen does not exist). Normal-bridged TRELLIS lineage, geometry-only, and the
authors removed the NVIDIA deps (kaolin/nvdiffrast/flexicubes) -> MIT-clean commercially.
Licence: MIT code; weights trellis-normal-v0-1 (MIT) + yoso-normal-v1-8-1 (Apache-2.0).
Runs inside the `hi3dgen` venv created by install_models.sh.

  python infer_hi3dgen.py manifest.json out/hi3dgen

Writes out/hi3dgen/<key>.glb per manifest item. One failure never aborts the batch.
"""
import sys, os, json, time, traceback
os.environ.setdefault("SPCONV_ALGO", "native")          # app.py sets this before any import

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

REPO = "/workspace/repos/Stable3DGen"
WEIGHTS = os.path.join(REPO, "weights")                 # app.py's cache_weights() layout
sys.path.insert(0, REPO)

import torch
from PIL import Image

# --- weights where app.py expects them (weights/<name>) -------------------------
from huggingface_hub import snapshot_download
os.makedirs(WEIGHTS, exist_ok=True)
for rid in ["Stable-X/trellis-normal-v0-1", "Stable-X/yoso-normal-v1-8-1", "ZhengPeng7/BiRefNet"]:
    local = os.path.join(WEIGHTS, rid.split("/")[-1])
    if not os.path.exists(local):
        snapshot_download(repo_id=rid, local_dir=local)

# --- load pipeline + normal predictor ONCE ---------------------------------------
print("[hi3dgen] loading Hi3DGenPipeline (weights/trellis-normal-v0-1) ...", flush=True)
from hi3dgen.pipelines import Hi3DGenPipeline
pipe = Hi3DGenPipeline.from_pretrained(os.path.join(WEIGHTS, "trellis-normal-v0-1"))
pipe.cuda()
print("[hi3dgen] loading StableNormal_turbo (yoso-normal-v1-8-1) via torch.hub ...", flush=True)
normal_predictor = torch.hub.load("hugoycj/StableNormal", "StableNormal_turbo",
                                  trust_repo=True, yoso_version="yoso-normal-v1-8-1",
                                  local_cache_dir=WEIGHTS)
print(f"[hi3dgen] loaded. {len(items)} inputs.", flush=True)

for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[hi3dgen] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = Image.open(os.path.join(BUNDLE, it["input"])).convert("RGB")
        img = pipe.preprocess_image(img, resolution=1024)
        normal = normal_predictor(img, resolution=768, match_input_resolution=True, data_type="object")
        outputs = pipe.run(normal, seed=42, formats=["mesh"], preprocess_image=False,
                           # gradio defaults per app.py sliders — VERIFY on the pod (manual issue #7)
                           sparse_structure_sampler_params={"steps": 12, "cfg_strength": 7.5},
                           slat_sampler_params={"steps": 12, "cfg_strength": 3.0})
        mesh = outputs["mesh"][0] if isinstance(outputs, dict) else outputs[0]
        if hasattr(mesh, "to_trimesh"):
            mesh = mesh.to_trimesh(transform_pose=True)   # app.py export path
        mesh.export(out)
        print(f"[hi3dgen] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[hi3dgen] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[hi3dgen] batch done.", flush=True)
