# Manual: PartCrafter (wgsxm, PKU/CMU) — 🟡 DRAFT — recipe not yet pod-proven (written 2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + `scripts/inference_partcrafter.py` + HF API
> (fetched 2026-07-11), **not** from a completed pod run. Fill in the real fix chain after the first run.

> **Campaign note — gate failed (2026-07-12, A100):** PartCrafter got its one-engine slot in the
> `newwave.sh` queue; the 1-mesh preflight gate **failed on the draft recipe** and the slot was skipped
> by policy (see `logs/nw_partcrafter.log` on the pod volume). No mesh reached the catalog. **The DRAFT
> banner stands.**

**Status:** Licence-cleared in the Stage-7 audit ([HUGGINGFACE_MODEL_NARROWING.md](../../docs/HUGGINGFACE_MODEL_NARROWING.md));
queued for the next-wave pod run. **Structured PART-LEVEL generation**: one image → N separate part
meshes (a TripoSG-family DiT with part-aware attention — the inference helper is literally called
`run_triposg`). Uniquely interesting for furniture: drawers, doors, legs and tops arrive as *separate
components*, which is exactly what the IFC decomposition and the repair packs would love. Geometry-only.

## Licence (verbatim)

Code `LICENSE` (github.com/wgsxm/PartCrafter, fetched 2026-07-11):

> MIT License
>
> Copyright (c) 2025 Yuchen Lin

Weights `wgsxm/PartCrafter` (object-level) and `wgsxm/PartCrafter-Scene` (scene-level) — HF API tag
**`license:mit`**, `gated: False` (verified 2026-07-11). Code MIT + weights MIT → royalty-free, EU-safe.

**One dependency trap:** the official inference script background-removes with
**`briaai/RMBG-1.4`, whose HF licence tag is `license:other`** (Bria's own non-commercial-without-
agreement licence — verified 2026-07-11). Do **not** ship that path; our draft infer script swaps in
`rembg` (u2net), same as every other engine in the bundle. Also optional-only: the `--part_suggest`
flag calls the **Gemini API** (`google-genai` is in requirements) — skip it, pass `--num_parts` explicitly.

## Requirements
- Authors' env: **python 3.11, torch 2.5.1+cu124**; `settings/setup.sh` = `torch-cluster` from the PyG
  wheel index + `settings/requirements.txt` + `apt-get install libegl1 libegl1-mesa libgl1-mesa-dev`
  (rendering only).
- `settings/requirements.txt` pins: `numpy==1.26.4` (the numpy-war pin again), plus diffusers,
  transformers, einops, jaxtyping, typeguard (the TripoSG typing deps!), pyrender, and training bloat
  we can `|| true` past (deepspeed, wandb, google-genai).
- **VRAM (README, verbatim):** *"A CUDA-enabled GPU with at least 8GB VRAM"* — the lightest of the
  next wave. Memory scales with part count / tokens (default **1024 tokens/part**, 2048 for scenes).
- Repo: `https://github.com/wgsxm/PartCrafter` → `/workspace/repos/PartCrafter`
- Weights: `wgsxm/PartCrafter` (+ `briaai/RMBG-1.4` only if you keep their masking path — see licence note).
- **num_parts must be chosen per image** (1–16). No auto mode without the Gemini call; our draft infer
  script reads `PARTCRAFTER_PARTS` (default 4 — a sane furniture prior: top/legs/frame/door).

## Working install recipe (anticipated — fill from the run)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
python -m venv /workspace/envs/partcrafter --system-site-packages
source /workspace/envs/partcrafter/bin/activate
git clone --depth 1 https://github.com/wgsxm/PartCrafter /workspace/repos/PartCrafter
cd /workspace/repos/PartCrafter
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
pip install torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu124.html
pip install -r settings/requirements.txt
pip install rembg onnxruntime                       # our licence-clean masking (replaces RMBG-1.4)
apt-get install -y libegl1 libgl1-mesa-dev          # their setup.sh line (rendering utils)
python -c "from huggingface_hub import snapshot_download; snapshot_download('wgsxm/PartCrafter')"
```

## Run
Official CLI (from the README — downloads weights to `pretrained_weights/`, results to `./results/<tag>`):
```bash
python scripts/inference_partcrafter.py --image_path assets/images/np3_2f6ab901c5a84ed6bbdf85a67b22a2ee.png \
  --num_parts 3 --tag robot --render
```
Programmatic (assembled verbatim from `scripts/inference_partcrafter.py`):
```python
import sys, torch; sys.path.insert(0, "/workspace/repos/PartCrafter")
from src.pipelines.pipeline_partcrafter import PartCrafterPipeline
from huggingface_hub import snapshot_download
local = snapshot_download("wgsxm/PartCrafter")            # local-snapshot lesson, as with TripoSG
pipe = PartCrafterPipeline.from_pretrained(local).to("cuda", torch.float16)
outputs = pipe(image=[img_pil] * num_parts,               # the image is REPEATED once per part
               attention_kwargs={"num_parts": num_parts},
               num_tokens=1024,
               generator=torch.Generator(device=pipe.device).manual_seed(42),
               num_inference_steps=50, guidance_scale=7.0).meshes
# outputs = list of num_parts trimesh meshes; a decode failure yields None for that part
```
Batch driver: `deliverable/cloud_bundle/infer_partcrafter.py` (DRAFT) — merges the parts into one GLB
for the standard scorer, drops `None` parts.

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | masking path wants `pretrained_weights/RMBG-1.4` | their script hard-downloads briaai/RMBG-1.4 (`license:other` — Bria NC) | use our rembg/u2net foreground instead (the draft infer script already does) |
| 2 | `--part_suggest` errors about API keys | it calls Gemini (`google-genai`) to guess num_parts | never use it in the benchmark — pass `--num_parts`/`PARTCRAFTER_PARTS` explicitly |
| 3 | a part comes back `None` | decoding error acknowledged in their own script (they substitute a dummy mesh) | skip the part when merging; log how often it happens per category |
| 4 | scorer sees a multi-component GLB | part-level output is the whole point | merge parts (`trimesh.util.concatenate`) for F-score; keep the per-part GLBs for the IFC decomposition experiment |
| 5 | pyrender/EGL crash on the headless pod | `--render` uses pyrender | keep `PYOPENGL_PLATFORM=egl` (install_models.sh already exports it) or skip `--render` |
| 6 | deepspeed/wandb/google-genai install noise | training deps inside requirements | irrelevant at inference; let them fail soft (`|| true`) |
| 7 | jaxtyping/typeguard missing at import | TripoSG heritage (TripoSG.md fixes #2/#3) | both are in settings/requirements.txt — verify they landed |

## Verdict for the paper (anticipated)
The lightest (≥8 GB) and structurally most interesting next-wave model: nobody else gives us
*named-in-pieces* furniture, and part-level meshes map directly onto IFC decomposition and per-part
repair. MIT code + MIT weights, one licence landmine to route around (RMBG-1.4) and one API dependency
to ignore (Gemini part suggestion). Risk: per-part quality vs a single-mesh TripoSG, and the manual
num_parts choice per item. Scores TBD.
