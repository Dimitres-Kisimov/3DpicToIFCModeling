# Manual: Unique3D (AiuniAI) — 🟡 DRAFT · OPTIONAL CANDIDATE — not yet pod-proven (written 2026-07-11)

> **DRAFT — optional candidate.** Shorter manual on purpose: Unique3D is the *oldest* of the Stage-7
> wave (2024) and its weight distribution is the messiest, so it is documented as a fallback rather
> than queued ahead of Direct3D-S2/Step1X-3D/Hi3DGen/PartCrafter. Written from the repo README +
> LICENSE (fetched 2026-07-11), **not** from a pod run.

**What it is:** single image → **textured** mesh in ~30 s (multiview diffusion → normal diffusion →
mesh reconstruction + super-resolution texturing). MIT, fast, textured — the same pitch as Step1X-3D
but a generation older and much lighter.

## Licence (verbatim)

Code `LICENSE` (github.com/AiuniAI/Unique3D, fetched 2026-07-11):

> MIT License
>
> Copyright (c) 2024 AiuniAI

**Weights caveat (the real problem):** the README ships **no HuggingFace model repo id**. Checkpoints
come from *"huggingface spaces"* or a **Tsinghua Cloud Drive** link, manually unpacked into a `ckpt/`
tree (`controlnet-tile/`, `image2normal/`, `img2mvimg/`, `realesrgan-x4.onnx`, `v1-inference.yaml`).
An unversioned drive download means we cannot pin or licence-verify the exact weight files the way we
did for every other model (HF API tag check) — **verify the licence tag of whatever space/drive bundle
is actually downloaded before any non-benchmark use.** FLAGGED: install recipe below is unverified on
this point; do not invent a repo id.

## Requirements
- Authors' env: python 3.11, **CUDA 12.1**, `diffusers==0.27.2` (the InstantMesh-era pin),
  `mmcv-full` from the openmmlab index **built for torch 2.3.1/cu121** — a hard torch pin that will
  fight the pod base (universal gotcha #3). Windows install exists (`install_windows_win_py311_cu121.bat`)
  but is explicitly fiddly (Triton wheels + VS Build Tools).
- VRAM/runtime: not stated in the README (*"~30 seconds"* generation is the only number). Unrecorded.
- Repo: `https://github.com/AiuniAI/Unique3D` → `/workspace/repos/Unique3D`
- Entry point: **gradio-first** — `python app/gradio_local.py --port 7860`. No documented batch CLI;
  a bundle infer script would have to import the app's internal modules (deferred until the model is
  actually queued).

## Install (anticipated, from the README — verbatim commands)
```bash
python -m venv /workspace/envs/unique3d --system-site-packages
source /workspace/envs/unique3d/bin/activate
git clone --depth 1 https://github.com/AiuniAI/Unique3D /workspace/repos/Unique3D
cd /workspace/repos/Unique3D
pip install ninja
pip install diffusers==0.27.2
pip install mmcv-full -f https://download.openmmlab.com/mmcv/dist/cu121/torch2.3.1/index.html
pip install -r requirements.txt
# weights: download the ckpt bundle (HF space / Tsinghua drive) and unpack to ./ckpt/ — see caveat above
python app/gradio_local.py --port 7860
```

## Known input limitations (README, near-verbatim)
- Best on *"orthographic front-facing images with a rest pose"*; occlusions cause worse reconstructions.
- The input should contain the longest edge of the object, otherwise results come out *"squashed"*.
- The public demos are noted by the authors themselves as overcrowded / occasionally unstable.

## Anticipated issues
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | mmcv-full wheel wants torch 2.3.1 | openmmlab index is per-torch/cuda | venv-local torch 2.3.1+cu121; never let it near the base torch (gotcha #3) |
| 2 | no weights to download programmatically | no HF repo id published | manual ckpt/ unpack; record the exact source URL + hash in CREDITS.md when done |
| 3 | no batch entry point | gradio-only docs | write the infer script against `app/` internals only if the model is promoted from optional |

## Verdict for the paper (anticipated)
MIT + textured + fast is attractive on paper, but Step1X-3D covers the same "permissive textured"
slot with pinned HF weights, a documented python API, and current-generation quality — and Hi3DGen
covers the licence-cleanest-geometry slot. Keep Unique3D as the lightweight fallback if Step1X-3D's
27–29 GB VRAM floor proves fatal for the app's engine tiers. Scores TBD (not queued).
