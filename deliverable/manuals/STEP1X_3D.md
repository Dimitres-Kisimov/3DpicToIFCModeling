# Manual: Step1X-3D (StepFun) — 🟡 DRAFT — recipe not yet pod-proven (written 2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + HF API (fetched 2026-07-11), **not** from a
> completed pod run. Install steps and the issues table are *anticipated*; fill in the real fix chain
> after the first run, like the proven manuals (TripoSG.md, SAM3D.md).

**Status:** Licence-cleared in the Stage-7 audit ([HUGGINGFACE_MODEL_NARROWING.md](../../docs/HUGGINGFACE_MODEL_NARROWING.md));
queued for the next-wave pod run. Two-stage pipeline: **geometry** (1300M-param flow model, GLB out)
then **texture synthesis** on the untextured mesh. One of the very few **fully-permissive textured**
image-to-3D pipelines — that is its whole selling point vs TripoSG/Direct3D-S2.

## Licence (verbatim)

Code `LICENSE` (github.com/stepfun-ai/Step1X-3D, fetched 2026-07-11) is the stock Apache text:

> Apache License
> Version 2.0, January 2004

(The file is the unmodified Apache-2.0 template — the appendix boilerplate still reads
`Copyright [yyyy] [name of copyright owner]`.) The README badge states **"Apache License 2.0"**.
Weights `stepfun-ai/Step1X-3D` — HF API tag **`license:apache-2.0`**, `gated: False` (verified
2026-07-11). Code Apache-2.0 + weights Apache-2.0 → royalty-free, EU-safe.

**One commercial flag:** `requirements.txt` pulls **`git+https://github.com/NVlabs/nvdiffrast.git`**
(NVIDIA Source Code License — the same research-OK/commercial-flag we carry for TRELLIS and
InstantMesh) plus `kaolin==0.17.0` (Apache-2.0, fine). nvdiffrast appears to serve the **texture**
stage; whether the geometry-only path imports it is **unverified** — check on the pod.

## Requirements
- Authors' env: **python 3.10, torch 2.5.1+cu124** (`pip install torch==2.5.1 torchvision==0.20.1
  torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124`).
- **VRAM/runtime (README table, verbatim):** Geometry (1300m) + Texture = **27 GB, 152 s** (50 steps);
  Geometry-Label (1300m) + Texture = **29 GB, 152 s**. Geometry-only cost is not stated — measure it.
- Repo: `https://github.com/stepfun-ai/Step1X-3D` → `/workspace/repos/Step1X-3D`
- Heavy pinned `requirements.txt` (diffusers==0.32.2, transformers==4.48.0, numpy==1.26.4,
  pytorch-lightning==2.2.4, open3d==0.19.0, cupy-cuda12x, sageattention==1.0.6, …) **plus** git builds
  of nvdiffrast and pytorch3d, **plus** `torch-cluster` from the PyG wheel index, **plus** kaolin 0.17.0
  from the NVIDIA wheel index, **plus two repo-local compiled extensions** for the texture stage
  (`step1x3d_texture/custom_rasterizer`, `step1x3d_texture/differentiable_renderer`).
- Weights: `stepfun-ai/Step1X-3D` with subfolders **`Step1X-3D-Geometry-1300m`**,
  `Step1X-3D-Geometry-Label-1300m` (symmetry/geometry-type label control), **`Step1X-3D-Texture`**.

## Working install recipe (anticipated — fill from the run)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=9.0   # H200; A100=8.0
python -m venv /workspace/envs/step1x3d --system-site-packages
source /workspace/envs/step1x3d/bin/activate
git clone --depth 1 https://github.com/stepfun-ai/Step1X-3D /workspace/repos/Step1X-3D
cd /workspace/repos/Step1X-3D

pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt                     # long: builds nvdiffrast + pytorch3d from git
pip install torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu124.html
pip install kaolin==0.17.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu124.html

# texture-stage compiled extensions (skip if benchmarking geometry only):
( cd step1x3d_texture/custom_rasterizer && python setup.py install )
( cd step1x3d_texture/differentiable_renderer && python setup.py install )

python -c "from huggingface_hub import snapshot_download; snapshot_download('stepfun-ai/Step1X-3D')"
```

## Run (from the repo README — verbatim imports)
```python
# Stage 1 — geometry (what the benchmark scores):
from step1x3d_geometry.models.pipelines.pipeline import Step1X3DGeometryPipeline
geometry_pipeline = Step1X3DGeometryPipeline.from_pretrained(
    "stepfun-ai/Step1X-3D", subfolder='Step1X-3D-Geometry-1300m').to("cuda")
out = geometry_pipeline("examples/images/000.png", guidance_scale=7.5, num_inference_steps=50)
out.mesh[0].export("untexture_mesh.glb")

# Stage 2 — texture (optional for the benchmark, the reason to pick this model for the app):
from step1x3d_texture.pipelines.step1x_3d_texture_synthesis_pipeline import Step1X3DTexturePipeline
texture_pipeline = Step1X3DTexturePipeline.from_pretrained("stepfun-ai/Step1X-3D", subfolder="Step1X-3D-Texture")
textured_mesh = texture_pipeline("examples/images/000.png", untexture_mesh)
textured_mesh.export("textured_mesh.glb")
```
Batch driver: `deliverable/cloud_bundle/infer_step1x3d.py` (DRAFT) — geometry stage by default,
texture stage opt-in via `STEP1X_TEXTURE=1`.

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | `requirements.txt` install takes forever / dies at nvdiffrast or pytorch3d | both are **git source builds** inside the requirements file | `--no-build-isolation`, CUDA_HOME + nvcc on PATH (gotchas #1/#2); pytorch3d: consider the prebuilt-wheel route from SAM3D.md |
| 2 | pins drag in a second torch → `torchvision::nms does not exist` | the torch/torchvision version war (gotcha #3) | install torch 2.5.1+cu124 FIRST, re-check `pip show torch` after `-r requirements.txt`; reinstall offenders `--no-deps` |
| 3 | `sageattention` import/kernel error | pinned `sageattention==1.0.6` is a compiled-attention dep (same family as gotcha #6) | look for an sdpa/eager attention switch in the geometry config — **unverified**; texture stage may not need it |
| 4 | custom_rasterizer/differentiable_renderer `setup.py install` fails | repo-local CUDA extensions, wrong arch | export `TORCH_CUDA_ARCH_LIST` for the actual GPU before building; only needed for the texture stage |
| 5 | 27–29 GB VRAM with texture | README's own numbers | fits A100/H200 only; geometry-only may fit smaller — measure and record for the app's VRAM gating |
| 6 | full snapshot is huge (geometry + label + texture subfolders) | three model variants in one HF repo | `snapshot_download(..., allow_patterns=["Step1X-3D-Geometry-1300m/*"])` for the benchmark |
| 7 | kaolin wheel 404 | wheel index is per-torch/cuda | keep torch **2.5.1+cu124** exactly, or rebuild the kaolin index URL for the actual pair |

## Verdict for the paper (anticipated)
The only fully-permissive (Apache code **and** weights) **textured** generator on the list — if its
geometry scores anywhere near TripoSG it becomes the default "generate" fallback for the app, since it
skips the repair-then-retexture problem entirely. Costs: the heaviest dependency stack of the next wave
(two git source builds + two repo-local CUDA extensions + three wheel indexes), 27–29 GB VRAM with
texture, ~152 s/asset (vs TripoSG's 7–16 s), and an nvdiffrast (NVIDIA-licence) dependency to isolate
on the texture path. Scores TBD.
