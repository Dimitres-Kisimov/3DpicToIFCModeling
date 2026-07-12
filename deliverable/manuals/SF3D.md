# Manual: Stable Fast 3D — SF3D (Stability AI) — ✅ WORKS (pod-proven 2026-07-12, A100)

**Status:** ✅ **Working** — research-10, the full 187-item comparison sweep, **and** the raw-vs-cutout
A/B (`out_seg`) all completed on the 2026-07-11→12 A100 campaign; **192 SF3D items** landed in the final
IFC-gated catalog (third full-sweep engine alongside TripoSG and TRELLIS). Single-image → **textured**
GLB in one fast pass (its own rembg cutout + UV unwrap + texture bake).
**Licence: Stability Community License** — free below US$1M annual revenue. Fine for this internal
benchmark; a production adoption needs the licence check recorded (see MODEL_SURVEY_SCS.md §8).
Weights are **HF-gated** — the gate is real and it wasted a whole night slot (fix #1).

## Requirements
- torch 2.x (pod base is fine), CUDA toolkit on PATH (`CUDA_HOME=/usr/local/cuda`),
  `TORCH_CUDA_ARCH_LIST=8.0` (A100; H200 = `9.0`), and a `TMPDIR` with **disk headroom** for the
  vendored-extension builds (fix #2).
- Repo: `https://github.com/Stability-AI/stable-fast-3d` → `/workspace/repos/stable-fast-3d`
- Weights: `stabilityai/stable-fast-3d` (**gated** — accept the licence on the model page with the
  **same account as the token**, then verify with a real file download, fix #1).
- Vendored compiled extensions **inside the repo**: `./uv_unwrapper`, `./texture_baker` (CUDA/C++ —
  both need `--no-build-isolation`, fix #2).
- `transformers==4.49.*` (fix #3), `open_clip_torch` (fix #4), `rembg`, `onnxruntime`.

## Working install recipe (campaign-proven)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0
export TMPDIR=/workspace/tmp && mkdir -p $TMPDIR          # build headroom (fix #2)
python -m venv /workspace/envs/sf3d --system-site-packages
source /workspace/envs/sf3d/bin/activate                  # ALL deps go into THIS venv (fix #5)
git clone --depth 1 https://github.com/Stability-AI/stable-fast-3d /workspace/repos/stable-fast-3d
cd /workspace/repos/stable-fast-3d
pip install -r requirements.txt
pip install rembg onnxruntime open_clip_torch "transformers==4.49.*"   # fixes #3, #4
pip install --no-build-isolation ./uv_unwrapper                        # fix #2
pip install --no-build-isolation ./texture_baker                       # fix #2
# gate check with a REAL download, not model_info (fix #1):
python -c "from huggingface_hub import hf_hub_download; \
hf_hub_download('stabilityai/stable-fast-3d', 'config.yaml')"
```

## Run
Entrypoint (from `infer_sf3d.py` — loads once, loops the manifest, one failure never aborts the batch):
```python
import sys; sys.path.insert(0, "/workspace/repos/stable-fast-3d")
from sf3d.system import SF3D
from sf3d.utils import remove_background, resize_foreground
model = SF3D.from_pretrained("stabilityai/stable-fast-3d",
                             config_name="config.yaml", weight_name="model.safetensors")
model.to("cuda"); model.eval()
img = remove_background(img, rembg_session)      # sf3d expects an RGBA foreground cutout
img = resize_foreground(img, 0.85)
mesh, _meta = model.run_image(img, bake_resolution=1024)   # under torch.autocast bfloat16
mesh.export("x.glb", include_normals=True)
```
```bash
cd /workspace/cloud_bundle
/workspace/envs/sf3d/bin/python infer_sf3d.py manifest.json out/sf3d
# raw-vs-cutout A/B: run again with --out out_seg (sf3d does its own rembg, so both variants score)
```

## Issues hit and the fixes — 2026-07-11→12 A100 campaign

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | weights **403 with a valid token**, while hub metadata calls succeed — cost a full night slot (`MK_SF3D_STILL_BLOCKED`) | the **HF gate is real**, and metadata-level API checks (`model_info`) **pass even when file downloads 403** — "access looks fine" is a false negative | the account owner must **accept the licence on huggingface.co/stabilityai/stable-fast-3d**; then **verify access with an actual file download** (`hf_hub_download`), never `model_info` (makeup_slots.sh → night_shift.sh once the user accepted). *verified 2026-07-12 (A100)* |
| 2 | `uv_unwrapper` / `texture_baker` builds fail — `No module named 'torch'`, or the build dies with no space in `/tmp` | both are **vendored CUDA/C++ source builds inside the repo**: build isolation hides the venv's torch, and the default tmpdir lacks build headroom on a 30 GB container disk | `pip install --no-build-isolation ./uv_unwrapper ./texture_baker` with `CUDA_HOME` + `TORCH_CUDA_ARCH_LIST` set and **`TMPDIR` pointed at a disk with headroom** (fix_round3.sh; queue4_rebuild.sh slot 2). *verified 2026-07-12 (A100)* |
| 3 | `ImportError: cannot import name 'find_pruneable_heads_and_indices' from 'transformers...'` | **transformers 5.x removed `find_pruneable_heads_and_indices`**, which SF3D still imports | pin **`transformers==4.49.*`**. *verified 2026-07-12 (A100)* |
| 4 | `ModuleNotFoundError: open_clip` | `open_clip_torch` is required on the image-conditioning path but is not resolved by the repo's requirements on this stack | `pip install open_clip_torch`. *verified 2026-07-12 (A100)* |
| 5 | the env repeatedly "loses" pure-python deps between slots (transformers et al. keep vanishing) | the venv is **`--system-site-packages`**: deps that landed in the *system* python get churned by other engines' installs — the venv only *appeared* to have them | install every dep **INTO the venv itself** (the venv's own pip, never the system pip); night_shift2.sh keeps a generic import→install chase loop as the safety net. *verified 2026-07-12 (A100)* |

## Verdict for the paper
The cheapest textured full-sweep engine of the campaign: 192 catalog items, fast single-pass inference,
own background removal, textured GLB out of the box. The two real costs are **operational, not
algorithmic**: a human-in-the-loop HF licence gate (#1) and vendored CUDA builds (#2). Licence is
revenue-capped (Stability Community License) — benchmark-tier here, flag for any production adoption.
