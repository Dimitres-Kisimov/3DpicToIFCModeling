# Manual: Cupid (cupid3d / Binbin Huang, CVPR '26 Highlight) — 🟡 DRAFT — census-trio candidate, not yet pod-proven (2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + HF API (all fetched 2026-07-11),
> **not** from a completed pod run. Install steps, entry point and the issues table are *anticipated*;
> fill in the real fix chain after the first run, like the proven manuals (TripoSG.md, SAM3D.md).

> **Campaign note (2026-07-12):** Cupid was **ON HOLD per user directive** before the new-engine queue
> ran (a safety check found no adverse signals — safetensors-only, MIT — but the hold stands
> regardless), so it **never received a slot**: nothing here is pod-verified either way. **The DRAFT
> banner stands.**

**Why we test it:** #2 of the three challengers from the full HuggingFace tag census
([HF_CENSUS_2026-07.md](../../docs/HF_CENSUS_2026-07.md)) — the only clean-licence model chasing
the same **reconstruction-fidelity** frontier as Pixal3D/SAM 3D (pose-grounded: jointly models the
object AND the camera, claims >3 dB PSNR / 10 % Chamfer over SOTA reconstruction), and it is
TRELLIS-format → cheap integration into our harness. High variance — benchmark before investing.

**NAMING TRAP:** the code lives at **`github.com/cupid3d/Cupid`** (released, CVPR '26 Highlight).
`github.com/hbb1/Cupid` is a **stale stub** whose README still says *"code … expected to be
released by January 2026"* (fetched 2026-07-11). The **weights** however ARE under the author's
HF handle: **`hbb1/Cupid`**. Clone from cupid3d, download from hbb1.

## Licence (verbatim)

Code `LICENSE` (github.com/cupid3d/Cupid, fetched 2026-07-11):

> MIT License
>
> Copyright (c) 2025 cupid3d

Weights `hbb1/Cupid` — HF API tag **`license:mit`**, `gated: False`, and
`base_model: microsoft/TRELLIS-text-xlarge` (finetune) — TRELLIS is MIT, so the lineage is clean
(verified 2026-07-11). Code MIT + weights MIT → royalty-free, EU-safe.
README notes submodules carry their own licences (diffoctreerast, modified FlexiCubes) — the same
TRELLIS-family caveat we already carry for TRELLIS itself; both are permissive but **verify the
FlexiCubes variant on the pod** (original FlexiCubes is NVIDIA Source Code License — non-commercial
use only in some builds; TRELLIS's own copy was the reason for the "NVIDIA-licensed compiled
renderer" flag in Study A).

## Requirements
- Python 3.8+, conda recommended by the README; **default torch 2.4.0 + CUDA 11.8**, CUDA 11.8 or
  12.2 tested. (Our pods run CUDA 12.x images — install the cu124 wheel of torch 2.4.0, the proven
  "official-base on newer driver" pattern from SAM3D.md #3 / Hi3DGen.)
- **VRAM (README, verbatim):** *"An NVIDIA GPU with at least 16GB of memory"* → fits the cheap 24 GB pod.
- Repo: `https://github.com/cupid3d/Cupid` (**`--recurse-submodules`** — it vendors TRELLIS-family
  extensions) → `/workspace/repos/Cupid`
- TRELLIS-family `setup.sh` with the compiled-dep parade **plus two extras vs SceneGen**:
  `--pytorch3d --moge` (pytorch3d = the SAM3D-grade build fight; MoGe = MS monocular geometry).
- Weights: `hbb1/Cupid` — downloaded automatically by `from_pretrained`, no token needed.

## Working install recipe (anticipated — fill from the run)
```bash
python -m venv /workspace/envs/cupid --system-site-packages
source /workspace/envs/cupid/bin/activate
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124
git clone --recurse-submodules https://github.com/cupid3d/Cupid /workspace/repos/Cupid
cd /workspace/repos/Cupid
# README command is `. ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast \
#   --spconv --mipgaussian --kaolin --nvdiffrast --pytorch3d --moge` — drop --new-env (conda):
. ./setup.sh --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast --pytorch3d --moge
pip install rembg onnxruntime
python -c "from huggingface_hub import snapshot_download; snapshot_download('hbb1/Cupid')"
```

## Loading API (from the repo's `example.py` — verbatim)
```python
os.environ['SPCONV_ALGO'] = 'native'

from cupid.pipelines import Cupid3DPipeline
from cupid.utils import render_utils, sample_utils, align_utils

pipeline = Cupid3DPipeline.from_pretrained("hbb1/Cupid")
pipeline.cuda()
image = sample_utils.load_image("assets/example_image/typical_creature_dragon.png")
outputs = pipeline.run(image)
# outputs keys: 'gaussian', 'radiance_field', 'mesh', 'pose'

from cupid.utils.align_utils import save_mesh
save_mesh(all_outputs=outputs, poses=outputs.pop('pose'), output_dir='output')
# → output/mesh{}.glb (textured) + metadata.json (camera extrinsics/intrinsics)
```
`example_multi.py` covers multi-image input. **A per-call `seed=` kwarg is unverified** — TRELLIS
pipelines accept one and Cupid is *"heavily built upon TRELLIS"* (README), so our draft driver
passes `seed=42` only if the `run` signature accepts it, plus `torch.manual_seed(42)` always.

Our batch driver: `deliverable/cloud_bundle/infer_cupid.py` (DRAFT) — `save_mesh` to a per-item
temp dir, first `mesh*.glb` renamed to `<key>.glb`; the pose/`metadata.json` sidecar is kept as
`<key>.pose.json` (Cupid's unique output — the camera pose our IFC placement stage could use).

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | `setup.sh` assumes conda (`--new-env`) | TRELLIS-family script | run inside the venv without `--new-env` |
| 2 | pytorch3d build failure | the classic (SAM3D install fight) | `pip install "git+https://github.com/facebookresearch/pytorch3d.git@stable" --no-build-isolation` with CUDA_HOME set |
| 3 | `flash_attn ... undefined symbol` | ABI (universal gotcha #6) | `ATTN_BACKEND=sdpa` (TRELLIS-family honours it) |
| 4 | spconv crash / wrong algo | tuned algo picks bad kernel | `SPCONV_ALGO=native` — the repo's own example pins it |
| 5 | `run()` rejects `seed=` | non-TRELLIS signature | fall back to `torch.manual_seed(42)` only; note in log |
| 6 | `save_mesh` writes unexpected file names | `mesh{}.glb` format string, count unknown | glob `*.glb` in the temp dir; if >1, take the first and log |
| 7 | output mesh in *camera* frame, not canonical | pose-grounded design — pose is a separate output | scorer runs ICP alignment anyway; keep `<key>.pose.json` for the paper |
| 8 | MoGe checkpoint download at first run | `--moge` dependency | pre-warm in install (accept the download); check its licence tag on the pod (MoGe-2 weights are MIT) |
| 9 | 16 GB stated but two-stage run OOMs at high res | coarse + refinement stages | reduce sampler steps / resolution knobs per README defaults; A5000 24 GB has headroom |

## Verdict for the paper (anticipated)
The census's fidelity bet: if pose-grounded reconstruction transfers from its benchmarks to
office furniture, Cupid could challenge SAM 3D's geometry wins with a **clean MIT stack** (no
SAM-licence review, no NC dependency — pending the FlexiCubes-variant check). Its camera-pose
output is also the only census-trio feature our IFC placement stage could consume directly.
Downside: zero community signal (0 likes at census time) and a TRELLIS-grade install. Scores TBD.
