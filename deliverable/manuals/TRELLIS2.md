# Manual: TRELLIS.2-4B (Microsoft) — 🟨 software-proven 2026-07-12, awaiting DINOv3 gate (separate repo)

**Status (2026-07-12, A100 campaign):** **Software proven — the full import gate passes
(`PIPELINE_OK`)** on the campaign-built env (torch 2.9.\*+cu128, sdpa, CuMesh + o-voxel rebuilt from
source), but **no mesh yet**: the pipeline's DINOv3 conditioning weights are **gated by Meta** and the
grant had not landed when the pod stopped (see confirmed issue #3). `trellis2_rebuild_retry.sh` holds the
complete from-zero rebuild+run that fires once the gate opens. **It is NOT the same codebase as
TRELLIS-v1** — different repo, different package (`trellis2`), different representation (field-free
**O-Voxel**, full PBR), different exporter (`o_voxel`). My initial install wrongly reused the v1 repo (it
can't load the .2-4B checkpoint). License MIT. **Needs ≥24 GB VRAM**, CUDA 12.4+ (we have 12.8).

## Requirements
- **torch 2.9.\*+cu128** — the cu128 build is mandatory on a CUDA-12.8 toolkit pod (confirmed issue #1);
  torch matched to torchvision (the v1 version-war fix #1 still applies), CUDA on PATH.
- Repo: **`https://github.com/microsoft/TRELLIS.2`** (NOT microsoft/TRELLIS) → `/workspace/repos/TRELLIS2`
- Package: `trellis2` + `o_voxel` (the exporter, compiled in-repo) + **CuMesh** (compiled from source).
  No xformers/flash_attn needed — `ATTN_BACKEND=sdpa` is the pod-proven import path.
- Weights: `microsoft/TRELLIS.2-4B` — **~16 GB measured** (not the ~8 GB guess; confirmed issue #4),
  **plus the gated `facebook/dinov3-*` conditioning weights** (confirmed issue #3).

## Loading API (from the HF model card)
```python
import sys; sys.path.insert(0, "/workspace/repos/TRELLIS2")
from trellis2.pipelines import Trellis2ImageTo3DPipeline
pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipeline.cuda()
mesh = pipeline.run(image)[0]
import o_voxel
glb = o_voxel.postprocess.to_glb(...)        # <-- exact args: read the repo's example script
glb.export("sample.glb", extension_webp=True)
```

## Working install recipe (campaign-proven to the import gate, 2026-07-12 — from `trellis2_rebuild_retry.sh`)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0  # A100
export TMPDIR=/workspace/tmp && mkdir -p $TMPDIR
python3 -m venv /opt/envs/trellis2 && source /opt/envs/trellis2/bin/activate
git clone --recurse-submodules https://github.com/microsoft/TRELLIS.2 /workspace/repos/TRELLIS2
bash install_models.sh trellis2                       # base deps per its setup.sh
pip uninstall -y xformers flash-attn                  # sdpa is the pod-proven path — no compiled attention
pip install "torch==2.9.*" torchvision --index-url https://download.pytorch.org/whl/cu128   # issue #1
# compiled extensions — from SOURCE, never from pip's wheel cache (issue #2):
git clone --recursive https://github.com/JeffreyXiang/CuMesh.git /workspace/tmp/CuMesh
pip install --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/tmp/CuMesh
pip install --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/repos/TRELLIS2/o-voxel
# import gate (this is what PIPELINE_OK means):
ATTN_BACKEND=sdpa python -c "import sys; sys.path.insert(0,'/workspace/repos/TRELLIS2'); \
from trellis2.pipelines import Trellis2ImageTo3DPipeline; print('PIPELINE_OK')"
# weights — only useful once the DINOv3 gate is granted (issue #3):
python -c "from huggingface_hub import snapshot_download; snapshot_download('microsoft/TRELLIS.2-4B')"
```

## Confirmed issues — 2026-07-11→12 A100 campaign

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | every compiled-extension build dies in torch's **`_check_cuda_version` hard error** | the pod's CUDA **toolkit is 12.8**; a **cu130 torch cannot compile extensions** against a 12.8 toolkit — it's a hard version check, not a warning | swap the env to **`torch==2.9.*` from the cu128 index**, then rebuild every extension (t2_torch_fix.sh, 5eaa86b). *verified 2026-07-12 (A100)* |
| 2 | CuMesh / o-voxel **still ABI-broken after the torch swap and a "rebuild"** | **pip's wheel cache** kept the wheels compiled against the previous torch and silently reused them — the "rebuild" installed the poisoned cache entry | always rebuild compiled extensions **from source** with `--no-cache-dir --no-build-isolation --force-reinstall` (t2_torch_fix.sh, trellis2_rebuild_retry.sh). *verified 2026-07-12 (A100)* |
| 3 | DINOv3 weights **403 with a valid token**, even though `model_info()` succeeds | `facebook/dinov3-*` is gated as a **Gating Group Collection** — metadata-level API checks (`model_info`) pass while actual file downloads 403 until Meta grants access | request access **before** scheduling any run; verify with a **real** `hf_hub_download(repo_id='facebook/dinov3-vitl16-pretrain-lvd1689m', filename='config.json')`, never `model_info` (trellis2_rebuild_retry.sh polls exactly this). *verified 2026-07-12 (A100)* |
| 4 | disk blows through the slot budget mid-download | `microsoft/TRELLIS.2-4B` weights are **~16 GB, not ~8** | budget a 16 GB weight slot; evict completed engines' envs/weights first (the rebuild script tears down sam3d/instantmesh envs and the trellis-v1 weights to make room). *verified 2026-07-12 (A100)* |

## Anticipated issues — still open (the mesh-generation half has not run yet)
| Likely symptom | Fix (from TRELLIS-v1 manual) |
|---|---|
| `torchvision::nms does not exist` | ~~`--no-deps` xformers~~ **superseded 2026-07-12**: xformers/flash_attn are dropped entirely — sdpa import path is pod-proven |
| missing transformers/open3d/utils3d/kaolin | install + stub kaolin check_tensor (#2–#5); on the A100 stack use the real kaolin-0.18 wheel (v1 manual #12) |
| nvdiffrast/diffoctreerast won't build | `--no-build-isolation` + CUDA_HOME (#6,#7) |
| `utils3d` API attribute error | install the **pinned commit** from TRELLIS.2's setup (#8) |
| `o_voxel.postprocess.to_glb(...)` arg error | read the repo's `example_image.py` for the exact call; or mesh-only export the `pipeline.run()` result |
| needs `diff_gaussian_rasterization` | mesh-only export fallback (v1 #9/#13 — Inria NC, licence-excluded) |

## Verdict for the paper
The newest, most-liked model (966 likes), MIT, full PBR + arbitrary topology. Highest integration cost
(separate repo + o_voxel + 4B weights). Treat as the stretch goal once the 4 simpler models are scored.
