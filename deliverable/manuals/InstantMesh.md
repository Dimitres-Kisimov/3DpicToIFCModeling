# Manual: InstantMesh (TencentARC) — ✅ WORKS (r10 10/10, F@0.02 = 0.328; sweep pod-proven 2026-07-12)

**Status:** ✅ **Working** — 10/10 research meshes (mean F@0.02 = **0.328**, 4th of 5 generators), and the
187-item comparison sweep completed on the 2026-07-11→12 A100 campaign **after three distinct
batch-killers were fixed** (see the confirmed table below — the sweep died at 0/187 twice before the
first fix landed). Two-stage (Zero123++ multiview diffusion → sparse-view LRM + FlexiCubes). Apache-2.0.
**Needs nvdiffrast** (NVIDIA license — research-use OK, commercial flag). On 80 GB the old 8 GB
"collapsed-cube" hack from the Windows attempt is NOT needed — it runs native at full resolution.

## Requirements
- torch 2.x, CUDA on PATH, `TORCH_CUDA_ARCH_LIST=9.0` (H200).
- Repo: `https://github.com/TencentARC/InstantMesh` → `/workspace/repos/InstantMesh`
- Pinned deps (InstantMesh is picky): `transformers==4.40.0 diffusers==0.27.2 huggingface_hub==0.23.0
  pytorch-lightning==2.1.2`, plus `einops omegaconf trimesh rembg onnxruntime imageio imageio-ffmpeg
  pillow numpy xatlas plyfile`, and **nvdiffrast**.
- Weights: `TencentARC/InstantMesh` (the customized Zero123++ UNet + the LRM checkpoint).

## Working install recipe (pod-proven — plus the recurring deps from confirmed issue #4)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=9.0
python -m venv /workspace/envs/instantmesh --system-site-packages
source /workspace/envs/instantmesh/bin/activate
git clone --depth 1 https://github.com/TencentARC/InstantMesh /workspace/repos/InstantMesh
pip install -q transformers==4.40.0 diffusers==0.27.2 huggingface_hub==0.23.0 pytorch-lightning==2.1.2 \
    einops omegaconf trimesh rembg onnxruntime imageio imageio-ffmpeg pillow numpy xatlas plyfile
pip install --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast.git"   # see TRELLIS manual #6/#7
```

## Run
`infer_instantmesh.py` stages all inputs into one dir and runs InstantMesh's `run.py` once (loads model
once), then collects `<name>.obj` and converts to `.glb`:
```bash
cd /workspace/cloud_bundle
/workspace/envs/instantmesh/bin/python infer_instantmesh.py manifest.json out/instantmesh
```

## Issues actually hit — 2026-07-11→12 A100 campaign (all confirmed on the 187-sweep)

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | sweep "completes" but collects **0/187 objs** (`MISSING obj` for every item) — hit **twice** | InstantMesh's `run.py` executes with **cwd = the repo**, so a **relative** outdir/staging path resolves against the repo, not the bundle — every obj landed somewhere else | **`os.path.abspath()` the outdir** before invoking `run.py` (754b0ac; baked into infer_instantmesh.py). *verified 2026-07-12 (A100)* |
| 2 | one photo kills the **entire single-process batch** partway through | Zero123++ **crashes on mode-'L'/grayscale images** (the list11 table photo), and `run.py` processes the whole staged dir in one process — one bad image aborts everything after it | **force-RGB at staging** (`Image.open(...).convert("RGB")`) in the driver, plus the same RGB normalization applied at the data level so every engine is protected (2608729). *verified 2026-07-12 (A100)* |
| 3 | sweep dies mid-batch with transient `OSError: [Errno 5]` on reads — killed the 187-sweep **twice** | the RunPod **network volume** throws transient Errno-5 I/O errors under load | **stage inputs on the CONTAINER disk** (`tempfile.mkdtemp()` in container /tmp, not the volume) with a 3× per-file retry (991c209). *verified 2026-07-12 (A100)* |
| 4 | import chain repeatedly broken across env rebuilds: `pytorch_lightning`, `xatlas`, then `nvdiffrast` | the same three deps go missing on every scripted rebuild — and **PyPI nvdiffrast is NOT the CUDA build** | chase loop: `pip install pytorch_lightning xatlas ninja`, then `pip install --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast"` (night_shift.sh, night_shift2.sh, makeup_slots.sh). *verified 2026-07-12 (A100)* |

## Anticipated issues (2026-07-01 draft) — what materialized
| Likely symptom | Outcome |
|---|---|
| `ModuleNotFoundError: nvdiffrast` | **confirmed, recurring** — see confirmed #4 (git CUDA build, never PyPI) |
| `diffusers` custom_pipeline error for Zero123++ | did not occur with the `diffusers==0.27.2` pin |
| OBJ→GLB texture loss | as expected — trimesh conversion, geometry is what's scored |
| pinned-version conflicts with base torch | did not bite here (but see SAM3D fix #16 — batch installs can silently bump torch) |

## Verdict for the paper
Apache-2.0 (cleaner than SAM 3D's custom license) but **needs nvdiffrast** like TRELLIS. The Zero123++
stage is stochastic (seed-dependent). Scored **0.328 mean F@0.02** (4th of 5, ahead of TripoSR) — the
"thin-structure" weakness (FlexiCubes) shows as expected. Operationally the most fragile batch engine of
the campaign: a single-process directory batch means **one bad input or one relative path kills all 187**
(confirmed issues #1–#3).
