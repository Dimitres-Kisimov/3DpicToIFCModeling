# Manual: TripoSG (VAST-AI) — ✅ WORKS

**Status:** Fully working — generated **10/10** furniture meshes. **Mean F@0.02 = 0.393** (beats both
TripoSR variants: 0.278 SAM2 / 0.295 rembg). Geometry-only (untextured), MIT licensed, **no nvdiffrast**.
**Per-mesh time:** ~7–16 s on H200. **Best item:** stool F=0.99; **weak:** flat pieces (table 0.10, desk 0.09).

## Requirements
- torch **2.8.0+cu128** (base), CUDA 12.8 toolkit on PATH, ≥8 GB VRAM (we used H200).
- Repo: `https://github.com/VAST-AI-Research/TripoSG` → `/workspace/repos/TripoSG`
- Weights: `VAST-AI/TripoSG` (public, ~2 GB) + `RMBG-1.4` (or rembg for bg removal)
- Key extra deps the README omits: **`diso`** (CUDA-compiled DiffDMC mesher), **`jaxtyping`**, **`typeguard`**, **`accelerate`**

## Working install recipe
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
python -m venv /workspace/envs/triposg --system-site-packages
source /workspace/envs/triposg/bin/activate
git clone --depth 1 https://github.com/VAST-AI-Research/TripoSG /workspace/repos/TripoSG
pip install -q diffusers transformers einops trimesh numpy scipy pillow huggingface_hub \
    omegaconf rembg onnxruntime opencv-python-headless accelerate
pip install --no-build-isolation diso        # <-- CUDA compile; needs CUDA_HOME + nvcc on PATH
pip install -q jaxtyping typeguard            # <-- pulled in by triposg.utils.typing
python -c "from huggingface_hub import snapshot_download; snapshot_download('VAST-AI/TripoSG')"
```

## Run (load once, loop inputs)
```python
import sys, torch; sys.path.insert(0, "/workspace/repos/TripoSG")
from huggingface_hub import snapshot_download
local = snapshot_download("VAST-AI/TripoSG")            # MUST load from a LOCAL dir, not the repo id
from triposg.pipelines.pipeline_triposg import TripoSGPipeline
pipe = TripoSGPipeline.from_pretrained(local).to("cuda", torch.float16)
# per image (rembg-cleaned RGB): out = pipe(image=img, num_inference_steps=50, guidance_scale=7.0); mesh=...; mesh.export("x.glb")
```

## Issues I hit (chronological) and the fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `ModuleNotFoundError: No module named 'diso'` | `diso` (the DiffDMC mesher) not in the README install list | `pip install --no-build-isolation diso` (plain `pip install diso` fails: its isolated build can't see torch → "No module named 'torch'") |
| 2 | `ModuleNotFoundError: No module named 'jaxtyping'` | `triposg/utils/typing.py` imports it | `pip install jaxtyping` |
| 3 | `ModuleNotFoundError: No module named 'typeguard'` | same file | `pip install typeguard` |
| 4 | `ValueError: scheduler/triposg.schedulers.scheduling_rectified_flow.py … does not exist in VAST-AI/TripoSG` | `TripoSGPipeline.from_pretrained("VAST-AI/TripoSG")` (HF repo id) can't resolve the custom scheduler; the diffusers fallback also fails | **Load from a LOCAL snapshot:** `d = snapshot_download("VAST-AI/TripoSG"); TripoSGPipeline.from_pretrained(d)` — the custom pipeline needs the repo structure on disk + the `triposg` package on `sys.path` |
| 5 | `accelerate was not found` warning (non-fatal) | optional speed/memory dep | `pip install accelerate` |

## Verdict for the paper
**Easiest of the cloud models to get running**, and the only generative one with **no compiled
rendering dependency** (no nvdiffrast) → cleanest commercially. Quality beats TripoSR on average but is
*spiky* (great on chairs/stools, poor on flat desks/tables — the thin/planar-surface failure mode).
