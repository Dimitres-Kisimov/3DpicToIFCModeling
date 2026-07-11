# Manual: Direct3D-S2 (DreamTechAI) — 🟡 DRAFT — recipe not yet pod-proven (written 2026-07-11)

> **DRAFT.** This manual is written from the repo README + LICENSE + HF API (all fetched 2026-07-11),
> **not** from a completed pod run. Install steps, entry point and the issues table are *anticipated*;
> fill in the real fix chain after the first run, like the proven manuals (TripoSG.md, SAM3D.md).

**Status:** Licence-cleared in the Stage-7 audit ([HUGGINGFACE_MODEL_NARROWING.md](../../docs/HUGGINGFACE_MODEL_NARROWING.md));
queued for the next-wave pod run. **Gigascale sparse-SDF geometry** (512³ or 1024³ SDF resolution) —
the highest-resolution *untextured* generator on the shortlist. Single-image → mesh, `.obj` export in
the README example. Was already on the Stage-3 shortlist before this second audit.

## Licence (verbatim)

Code `LICENSE.txt` (github.com/DreamTechAI/Direct3D-S2, fetched 2026-07-11):

> MIT License
>
> Copyright (c) 2025 DreamTechAI

Weights `wushuang98/Direct3D-S2` — HF API tag **`license:mit`**, `gated: False` (verified 2026-07-11).
Code MIT + weights MIT → royalty-free, EU-safe. No gate, no revenue cap.

## Requirements
- **torch 2.5.1+cu121** is the repo's tested base (`pip install torch==2.5.1 torchvision==0.20.1
  --index-url https://download.pytorch.org/whl/cu121`) — same official-base lesson as SAM3D.md #3
  (cu121 runs fine on a newer driver). Ubuntu 22.04 / CUDA 12.1 tested by the authors.
- **VRAM (README, verbatim):** *"Generating at 512 resolution requires at least 10GB of VRAM, and
  1024 resolution needs around 24GB."*
- Repo: `https://github.com/DreamTechAI/Direct3D-S2` → `/workspace/repos/Direct3D-S2`
- **Compiled deps (three!):** `torchsparse` (built from `mit-han-lab/torchsparse` source),
  the repo-local `third_party/voxelize/` extension (it is *inside* requirements.txt as a path),
  and `flash-attn` (also in requirements.txt — the known wheel-ABI landmine, universal gotcha #6).
- Notable pins from `requirements.txt`: `transformers==4.40.2`, `triton==3.1.0`,
  `utils3d` from the EasternJournalist git (the TRELLIS-family pinned-utils3d lesson again),
  plus `pymeshfix pyvista igraph scikit-image trimesh omegaconf einops diffusers`.
- Weights: `wushuang98/Direct3D-S2`, **subfolder `direct3d-s2-v-1-1`** (~public, no token needed).

## Working install recipe (anticipated — fill from the run)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=9.0   # H200; A100=8.0
python -m venv /workspace/envs/direct3ds2 --system-site-packages
source /workspace/envs/direct3ds2/bin/activate
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121

# torchsparse builds from source and needs the sparsehash headers first:
apt-get install -y libsparsehash-dev
git clone --depth 1 https://github.com/mit-han-lab/torchsparse /workspace/repos/torchsparse
pip install --no-build-isolation /workspace/repos/torchsparse

git clone --depth 1 https://github.com/DreamTechAI/Direct3D-S2 /workspace/repos/Direct3D-S2
cd /workspace/repos/Direct3D-S2
# requirements.txt contains flash-attn AND a local path (third_party/voxelize) — install the
# pure-python bulk explicitly, then the compiled bits with --no-build-isolation:
pip install scikit-image trimesh omegaconf tqdm huggingface_hub einops numpy "transformers==4.40.2" \
    diffusers "triton==3.1.0" pymeshfix pyvista igraph rembg onnxruntime
pip install "git+https://github.com/EasternJournalist/utils3d.git"
pip install --no-build-isolation flash-attn          # gotcha #6 — if the ABI fight starts, see issue 3
pip install --no-build-isolation ./third_party/voxelize
pip install -e . --no-deps
python -c "from huggingface_hub import snapshot_download; snapshot_download('wushuang98/Direct3D-S2')"
```

## Loading API (from the repo README — verbatim)
```python
from direct3d_s2.pipeline import Direct3DS2Pipeline
pipeline = Direct3DS2Pipeline.from_pretrained(
  'wushuang98/Direct3D-S2',
  subfolder="direct3d-s2-v-1-1"
)
pipeline.to("cuda:0")
mesh = pipeline(
  'assets/test/13.png',
  sdf_resolution=1024,        # 512 (≥10 GB) or 1024 (~24 GB)
  remove_interior=True,
  remesh=False,
)["mesh"]
mesh.export('output.obj')
```
Batch driver: `deliverable/cloud_bundle/infer_direct3ds2.py` (DRAFT) — default `sdf_resolution=512`,
override with `D3S2_RES=1024`; exports `.glb` for the standard scorer.

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | torchsparse build dies with missing `sparsehash/dense_hash_map` | sparsehash headers not installed | `apt-get install -y libsparsehash-dev` **before** building torchsparse |
| 2 | `No module named 'torch'` during torchsparse/voxelize build | pip build isolation (universal gotcha #2) | `pip install --no-build-isolation <pkg>` with CUDA_HOME + nvcc on PATH |
| 3 | `flash_attn ... undefined symbol _ZN3c10...` | wheel built for a different torch (gotcha #6) | build against the venv torch (`--no-build-isolation`); check whether Direct3D-S2 has an sdpa/xformers attention fallback — **unverified** |
| 4 | `transformers` version conflict with base env | repo pins `transformers==4.40.2` | keep the pin inside the venv; venv shadows the base site-packages |
| 5 | 1024³ run OOMs on a 24 GB card | README says 1024 needs *around* 24 GB — no headroom | drop to `sdf_resolution=512`, or run on the A100/H200 |
| 6 | pipeline wants a **file path**, not a PIL image | README example passes a path string | save the rembg-cleaned cutout to a temp `.png` and pass that path (what the draft infer script does) |
| 7 | `.obj`-style output loses per-run metadata | README exports `.obj` | the returned `mesh` is trimesh-compatible → `.export('x.glb')` works; verify on the run |

## Verdict for the paper (anticipated)
The cleanest licence profile of the next wave (MIT code **and** MIT weights) with the highest claimed
geometry resolution (1024³ sparse SDF). Untextured — so it slots into the same
`mesh → repair pack → IFC` lane as TripoSG, and competes with it head-to-head on geometry. The 10 GB
@512³ floor also makes it the only next-wave model that could plausibly gate onto mid-range GPUs in the
app's engine selector. Three compiled deps (torchsparse, voxelize, flash-attn) = expect a SAM3D-grade
install fight. Scores TBD.
