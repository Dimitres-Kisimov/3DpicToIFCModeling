# Manual: SceneGen (SJTU, 3DV '26) — 🟡 DRAFT — census-trio candidate, not yet pod-proven (2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + HF API (all fetched 2026-07-11),
> **not** from a completed pod run. Install steps, entry point and the issues table are *anticipated*;
> fill in the real fix chain after the first run, like the proven manuals (TripoSG.md, SAM3D.md).

> **Campaign note — gate failed (2026-07-12, A100):** SceneGen got its one-engine slot in the
> `newwave.sh` queue (benchmark-only tier — VGGT-1B dependency is NC); the 1-mesh preflight gate
> **failed on the draft recipe** and the slot was skipped by policy (see `logs/nw_scenegen.log` on the
> pod volume). No mesh reached the catalog. **The DRAFT banner stands.**

**Why we test it:** #1 of the three challengers from the full HuggingFace tag census
([HF_CENSUS_2026-07.md](../../docs/HF_CENSUS_2026-07.md)) — purpose-built for **indoor/furniture**
content, single image + object masks → multi-asset **textured** scene in one feedforward pass,
16 GB VRAM stated (fits the app's gating range), TRELLIS SLat decoders.

**NAMING TRAP (like Hi3DGen):** the code lives at **`github.com/Mengmouxu/SceneGen`** —
`github.com/haoningwu3639/SceneGen` does **not** exist (404 verified 2026-07-11). The HF weight
repo IS under the co-author's handle: `haoningwu/SceneGen`.

## Licence (verbatim)

Code `LICENSE` (github.com/Mengmouxu/SceneGen, fetched 2026-07-11):

> MIT License
>
> Copyright (c) 2025 孟某旭

Weights `haoningwu/SceneGen` — HF API tag **`license:mit`**, `gated: False` (verified 2026-07-11).

**⚠️ LICENCE SURPRISE — the census's "MIT verified end-to-end" needs a footnote.** SceneGen's
checkpoint recipe requires **two auxiliary Meta checkpoints**, and one is NonCommercial:

| Checkpoint | HF API licence (2026-07-11) | Role |
|---|---|---|
| `facebook/sam2-hiera-large` | **apache-2.0** ✅ | interactive-demo mask drawing only — our benchmark supplies precomputed rembg masks, so likely avoidable |
| `facebook/VGGT-1B` | **cc-by-nc-4.0** ⛔ | geometry encoder inside the visual+geometric feature-aggregation module (per the paper) — likely used at **every** inference |

→ Code MIT + own weights MIT, but the pipeline as shipped pulls an **NC** checkpoint.
**Research benchmark only** until we verify on the pod whether VGGT-1B can be detached for
single-object inference. If it cannot, SceneGen is **not deployable** under our royalty-free rule
even though every SceneGen-authored artifact is MIT. (Same "taint by dependency" pattern as
PRM/Zero123++ in the census contradiction table.)

## Requirements
- Python 3.8+ (README; env not hard-pinned), **CUDA 12.1 tested** by the authors.
- **VRAM (README, verbatim):** *"An NVIDIA GPU with at least 16GB of memory is necessary.
  The code has been verified on NVIDIA A100 and RTX 3090 GPUs."* → fits the cheap 24 GB pod.
- Repo: `https://github.com/Mengmouxu/SceneGen` → `/workspace/repos/SceneGen`
- TRELLIS-family setup script (`setup.sh`) with the full compiled-dep parade:
  xformers, flash-attn, diffoctreerast, spconv, mipgaussian, kaolin, nvdiffrast —
  expect the universal gotchas #2/#6 (build isolation, flash-attn ABI).
- Checkpoints (HF card layout — all three go under `checkpoints/` in the repo):
  ```
  checkpoints/
  ├── sam2-hiera-large    ← facebook/sam2-hiera-large   (apache-2.0)
  ├── VGGT-1B             ← facebook/VGGT-1B            (⛔ cc-by-nc-4.0 — benchmark only)
  └── scenegen            ← haoningwu/SceneGen          (mit; ckpts/ + pipeline.json)
  ```

## Working install recipe (anticipated — fill from the run)
```bash
python -m venv /workspace/envs/scenegen --system-site-packages
source /workspace/envs/scenegen/bin/activate
git clone --recurse-submodules https://github.com/Mengmouxu/SceneGen /workspace/repos/SceneGen
cd /workspace/repos/SceneGen
# README command is `. ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast \
#   --spconv --mipgaussian --kaolin --nvdiffrast --demo` — drop --new-env (it makes a conda env;
# we're in a venv) and --demo (gradio, headless pod doesn't need it):
. ./setup.sh --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast
pip install rembg onnxruntime
mkdir -p checkpoints
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('haoningwu/SceneGen',          local_dir='checkpoints/scenegen')
snapshot_download('facebook/sam2-hiera-large',   local_dir='checkpoints/sam2-hiera-large')
snapshot_download('facebook/VGGT-1B',            local_dir='checkpoints/VGGT-1B')  # NC — benchmark only
PY
```

## Loading API (from the repo's `inference.py` — verbatim)
```python
pipeline = SceneGenImageToScenePipeline.from_pretrained("checkpoints/scenegen")
outputs = pipeline.run_scene(
    image=images,                      # LIST of per-object PIL images
    mask_image=mask_images,            # LIST of per-object PIL masks
    scene_image=scene_image,           # the full scene photo
    preprocess_image=True,
    sparse_structure_sampler_params={"steps": 25, "cfg_strength": 5.0,
                                     "cfg_interval": [0.5, 1.0], "rescale_t": 3.0},
    slat_sampler_params={"steps": 25, "cfg_strength": 5.0,
                         "cfg_interval": [0.5, 1.0], "rescale_t": 3.0},
    resorted_indices=restore_indices,
)
outputs["scene"].export(f"{scene_id}.glb")     # textured GLB
```
Batch mode in the repo reads `assets/masked_images_test/<scene>/` (object PNGs + `*mask*.png` +
`scene.jpg`); the interactive Gradio demo (`interactive_demo.py`) draws masks with SAM2.
**No seed parameter appears in the repo's own inference call** — determinism handling is a
verify-on-pod item (our draft driver pins `torch.manual_seed(42)` and passes `seed=42` only if
the signature accepts it).

Our batch driver: `deliverable/cloud_bundle/infer_scenegen.py` (DRAFT) — single-object protocol:
`image=[cutout]`, `mask_image=[masks/<key>.png]` (the SAM3D mask convention, `precompute_masks.py`),
`scene_image=` the full photo.

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | `setup.sh` starts building conda things / `conda: command not found` | README flag `--new-env` assumes conda | run inside the venv **without** `--new-env`; install the flag-groups' pip deps manually from setup.sh if it still misbehaves |
| 2 | `flash_attn ... undefined symbol` | wheel/torch ABI (universal gotcha #6) | `ATTN_BACKEND=sdpa` — TRELLIS-family code honours it |
| 3 | spconv CUDA mismatch | wrong `spconv-cuXXX` wheel | `pip install spconv-cu120` (or cu118) — TRELLIS lesson |
| 4 | pipeline errors loading `checkpoints/scenegen` | relative path — depends on CWD | pass the **absolute** repo path (`/workspace/repos/SceneGen/checkpoints/scenegen`); driver does this |
| 5 | import wants VGGT/SAM2 even in batch mode | `pipeline.json` wires the aggregation module | download both checkpoints (install script does); record whether a VGGT-free path exists → licence verdict |
| 6 | `run_scene` rejects `seed=` | repo's own script sets no seed | keep `torch.manual_seed(42)`; log that per-call seeding is unsupported |
| 7 | output GLB contains scene *layout* transforms | multi-asset scene exporter | for single-object items the scene = 1 asset; verify axes/scale against the scorer's ICP alignment |
| 8 | kaolin wheel not found for venv torch | kaolin's narrow torch matrix | install kaolin from the NVIDIA wheel index matching the torch that setup.sh installed (Step1X lesson) |

## Verdict for the paper (anticipated)
The census's most on-topic challenger: trained for indoor scenes/furniture, textured output, and
the only candidate that natively consumes our **precomputed masks**. 16 GB floor fits mid-range
gating. The VGGT-1B `cc-by-nc-4.0` dependency is the deal-breaker risk: if inference can't run
without it, SceneGen drops from "deployable engine candidate" to "benchmark reference only",
and the census's headline (11 EU-usable) loses one. Scores TBD.
