# Manual: MIDI-3D (VAST-AI) — 🟡 DRAFT · OPTIONAL CANDIDATE — not yet pod-proven (written 2026-07-11)

> **DRAFT — optional candidate.** Shorter manual on purpose: MIDI-3D is *multi-instance scene*
> generation, not the single-object contract the benchmark scores, so it is documented for the
> room-level future work rather than queued for the standard 10-item run. Written from the repo
> README + LICENSE + HF API (fetched 2026-07-11), **not** from a pod run.

**What it is:** one photo + a **segmentation map** → a full multi-object 3D scene GLB
(each instance a separate mesh, jointly generated so the layout is coherent). From the same org as
TripoSG (VAST-AI-Research). Optional textured mode via MV-Adapter.

## Licence (verbatim)

Code `LICENSE` (github.com/VAST-AI-Research/MIDI-3D, fetched 2026-07-11) is the stock Apache text:

> Apache License
> Version 2.0, January 2004
> http://www.apache.org/licenses/

README badge: **"Apache-2.0 license"**. Weights `VAST-AI/MIDI-3D` — HF API tag **`license:apache-2.0`**,
`gated: False` (verified 2026-07-11). Royalty-free, EU-safe. The optional textured path adds
`huanngzh/mv-adapter` (**`license:apache-2.0`**, verified); the helper mask script uses Grounded-SAM
(check its component licences before shipping that path).

## Requirements
- Authors' env: python 3.10; README installs **torch cu118** (`pip install torch torchvision
  --index-url https://download.pytorch.org/whl/cu118`) — on our CUDA-12.8 pods use the cu121/cu124
  wheels instead and note the deviation.
- **VRAM (README, verbatim):** textured generation needs *"about 30G of VRAM"*. Geometry-only scene
  mode not stated — measure.
- Repo: `https://github.com/VAST-AI-Research/MIDI-3D` → `/workspace/repos/MIDI-3D`; weights
  auto-download to `pretrained_weights/MIDI-3D`.
- **Input contract difference:** every run needs `--rgb` **and** `--seg` (an instance-segmentation
  image). Masks come from their gradio UI or `python -m scripts.grounding_sam --image <image>
  --labels <labels> --output ./`.

## Install + run (anticipated, from the README — verbatim commands)
```bash
python -m venv /workspace/envs/midi3d --system-site-packages
source /workspace/envs/midi3d/bin/activate
git clone --depth 1 https://github.com/VAST-AI-Research/MIDI-3D /workspace/repos/MIDI-3D
cd /workspace/repos/MIDI-3D
pip install -r requirements.txt
# 1) make a segmentation map for the photo:
python -m scripts.grounding_sam --image input.jpg --labels "chair. desk. bookshelf" --output ./
# 2) image + seg -> multi-instance scene:
python -m scripts.inference_midi --rgb input.jpg --seg seg.png --output-dir "./"   # -> output.glb
# optional textured scene (needs MV-Adapter, ~30 GB VRAM):
pip install git+https://github.com/huanngzh/MV-Adapter
python -m scripts.image_to_textured_scene --rgb_image input.jpg --seg_image seg.png --seed 42 --output output
```

## Why there is NO `infer_midi3d.py` in the bundle (yet)
The benchmark contract is *one object image → one GLB scored against one ground-truth mesh*. MIDI-3D
wants a labelled segmentation per image and emits a *scene*; scoring it with `eval_accuracy.py` would
be apples-to-oranges. If we pursue it, the right experiment is the **SCS room photo → whole-room IFC**
track (it would compete with our detect→retrieve→place spine, not with the per-object generators),
with a manifest that carries per-image label prompts for `grounding_sam`.

## Anticipated issues
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | cu118 wheels on a CUDA-12.8 pod | README targets cu118 | install the cu121/cu124 torch pair instead; record what actually worked |
| 2 | grounding_sam model downloads | Grounded-SAM checkpoints | pre-warm; verify each checkpoint's licence before any shipped use |
| 3 | 30 GB VRAM (textured) | README's own number | A100/H200 only; geometry scene mode may be lighter — measure |

## Verdict for the paper (anticipated)
The only licence-clean **whole-scene** candidate — a future bridge from per-object generation to the
room-level SCS goal. Keep as an optional research track; do not mix its numbers into the per-object
benchmark tables.
