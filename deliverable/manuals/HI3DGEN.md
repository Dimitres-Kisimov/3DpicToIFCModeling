# Manual: Hi3DGen / Stable3DGen (Stable-X) — 🟡 DRAFT — recipe not yet pod-proven (written 2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + `app.py` + HF/GitHub APIs (fetched 2026-07-11),
> **not** from a completed pod run. Fill in the real fix chain after the first run.

**Status:** Licence-cleared in the Stage-7 audit ([HUGGINGFACE_MODEL_NARROWING.md](../../docs/HUGGINGFACE_MODEL_NARROWING.md));
queued for the next-wave pod run. **Normal-bridged geometry**: image → normal map (StableNormal_turbo)
→ TRELLIS-style sparse-structure + SLAT sampling → mesh. Geometry-only (`formats=["mesh"]`).
**Naming trap:** the *paper/project* is **Hi3DGen**, but **`github.com/Stable-X/Hi3DGen` does not exist**
(GitHub API returns nothing, verified 2026-07-11) — the code lives at
**`github.com/Stable-X/Stable3DGen`**. Clone that.

## Licence (verbatim)

Code `LICENSE` (github.com/Stable-X/Stable3DGen, fetched 2026-07-11):

> MIT License
>      Copyright (c) 2025 Bytedance Inc.

(Yes — the copyright holder is **Bytedance Inc.**, not "Stable-X"; record it as-is for the credits
file.) README, verbatim: *"The model and code of Stable3DGen are adapted from Trellis, which are
licensed under the MIT License"*, and the authors *"have specifically removed its dependencies on
certain NVIDIA libraries (kaolin, nvdiffrast, flexicube)"* — i.e. this is the **TRELLIS lineage minus
the NVIDIA-licence commercial flag** we carry for TRELLIS v1/InstantMesh.

Weights (HF API, verified 2026-07-11): `Stable-X/trellis-normal-v0-1` = **`license:mit`**;
`Stable-X/yoso-normal-v1-8-1` = **`license:apache-2.0`**; both `gated: False`. Runtime it also pulls
`ZhengPeng7/BiRefNet` (MIT) for foreground masking and the `hugoycj/StableNormal` torch.hub repo
(Apache-2.0) for the normal predictor. All royalty-free, EU-safe.

## Requirements
- Authors' env: **python 3.10, torch 2.4.0 + torchvision 0.19.0** (pinned!), `spconv-cu{ver}==2.3.6`,
  `xformers==0.0.27.post2` — note these pins are **older than the pod base torch 2.8**: this is the
  version-war setup (universal gotcha #3). Give it a venv-local torch 2.4.0 and don't let anything bump it.
- `requirements.txt`: `diffusers>=0.28.0`, `transformers==4.46.3`, `timm==0.6.7`, `kornia==0.8.0`,
  `numpy==1.26.4` (the SAM3D numpy-war pin again), `accelerate`, `triton`, `trimesh`, `scikit-image`, …
- **No kaolin, no nvdiffrast, no flexicubes** — by design (see licence section). Expect only the
  spconv/xformers compiled deps.
- VRAM: **not stated in the README** — unrecorded. TRELLIS-image-large lineage ran in ~16 GB here
  (TRELLIS.md), so budget that as a working estimate and *measure on the pod*.
- Repo: `https://github.com/Stable-X/Stable3DGen` (`--recursive`) → `/workspace/repos/Stable3DGen`
- Weights layout: `app.py` `cache_weights()` snapshot-downloads the three HF repos into
  `<repo>/weights/<name>` and loads the pipeline **from the local folder** `weights/trellis-normal-v0-1`.

## Working install recipe (anticipated — fill from the run)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
python -m venv /workspace/envs/hi3dgen --system-site-packages
source /workspace/envs/hi3dgen/bin/activate
git clone --recursive https://github.com/Stable-X/Stable3DGen /workspace/repos/Stable3DGen
cd /workspace/repos/Stable3DGen
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124
pip install spconv-cu124==2.3.6 || pip install spconv-cu120==2.3.6
pip install --no-deps xformers==0.0.27.post2        # matched to torch 2.4.0; --no-deps per gotcha #3
pip install -r requirements.txt
# pre-cache the three weight repos where app.py expects them (weights/<name>):
python - <<'EOF'
from huggingface_hub import snapshot_download
for rid in ["Stable-X/trellis-normal-v0-1", "Stable-X/yoso-normal-v1-8-1", "ZhengPeng7/BiRefNet"]:
    snapshot_download(repo_id=rid, local_dir="weights/" + rid.split("/")[-1])
EOF
```

## Run (assembled verbatim from `app.py`)
```python
import os; os.environ['SPCONV_ALGO'] = 'native'          # app.py sets this before any import
import sys, torch; sys.path.insert(0, "/workspace/repos/Stable3DGen")
from hi3dgen.pipelines import Hi3DGenPipeline
hi3dgen_pipeline = Hi3DGenPipeline.from_pretrained("weights/trellis-normal-v0-1")   # LOCAL folder
hi3dgen_pipeline.cuda()
normal_predictor = torch.hub.load("hugoycj/StableNormal", "StableNormal_turbo",
                                  trust_repo=True, yoso_version='yoso-normal-v1-8-1',
                                  local_cache_dir='./weights')
image = hi3dgen_pipeline.preprocess_image(image, resolution=1024)
normal_image = normal_predictor(image, resolution=768, match_input_resolution=True, data_type='object')
outputs = hi3dgen_pipeline.run(normal_image, seed=42, formats=["mesh",], preprocess_image=False,
    sparse_structure_sampler_params={"steps": 12, "cfg_strength": 7.5},   # gradio defaults — VERIFY
    slat_sampler_params={"steps": 12, "cfg_strength": 3.0})
trimesh_mesh = outputs['mesh'][0].to_trimesh(transform_pose=True)
trimesh_mesh.export("x.glb")
```
Batch driver: `deliverable/cloud_bundle/infer_hi3dgen.py` (DRAFT).

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | cloned `Stable-X/Hi3DGen` → 404 | the repo is named **Stable3DGen** | clone `github.com/Stable-X/Stable3DGen` |
| 2 | `torchvision::nms does not exist` / silent torch bump | pinned torch 2.4.0 vs pod base 2.8 (gotcha #3) | venv-local torch 2.4.0+cu124; `--no-deps xformers==0.0.27.post2`; re-check `pip show torch` after every install |
| 3 | spconv wheel not found | `spconv-cu{ver}` naming | try `spconv-cu124==2.3.6`, fall back `spconv-cu120==2.3.6` (worked for TRELLIS on the CUDA-12 image) |
| 4 | `torch.hub.load` hangs/fails on the pod | no internet or `trust_repo` prompt | pass `trust_repo=True`; pre-download once and use `source='local'` with `hub.get_dir()` (app.py shows both variants) |
| 5 | pipeline load fails from the HF id | `from_pretrained("Stable-X/trellis-normal-v0-1")` remote path untested here | load from the **local `weights/trellis-normal-v0-1` folder** exactly like app.py (same local-snapshot lesson as TripoSG fix #4) |
| 6 | attention backend import error | TRELLIS lineage → flash_attn/xformers switch | it inherits TRELLIS's backend env vars; force `ATTN_BACKEND=sdpa` if xformers misbehaves (universal gotcha #6) |
| 7 | sampler-params defaults unknown | README shows no numeric defaults | read the gradio sliders in `app.py` on the pod and record the real defaults here |

## Verdict for the paper (anticipated)
The licence-cleanest way to keep a TRELLIS-class generator: same SLAT machinery, but the authors
deleted kaolin/nvdiffrast/flexicubes specifically so it can be used commercially under MIT — removing
the one flag we carry on TRELLIS v1 and InstantMesh. The normal-bridging step is also an interesting
robustness hedge for the app's real photos (normals abstract away texture/lighting). Geometry-only, so
it lands in the repair-pack lane. VRAM unrecorded → measure. Scores TBD.
