# Manual: InstantMesh (TencentARC) — ⏳ pending

**Status:** Installed (repo cloned, base deps), **not yet run**. Two-stage (Zero123++ multiview diffusion
→ sparse-view LRM + FlexiCubes). Apache-2.0. **Needs nvdiffrast** (NVIDIA license — research-use OK,
commercial flag). On the H200's 80+ GB the 8 GB "collapsed-cube" hack from the old Windows attempt is NOT
needed — it should run native at full resolution.

## Requirements
- torch 2.x, CUDA on PATH, `TORCH_CUDA_ARCH_LIST=9.0` (H200).
- Repo: `https://github.com/TencentARC/InstantMesh` → `/workspace/repos/InstantMesh`
- Pinned deps (InstantMesh is picky): `transformers==4.40.0 diffusers==0.27.2 huggingface_hub==0.23.0
  pytorch-lightning==2.1.2`, plus `einops omegaconf trimesh rembg onnxruntime imageio imageio-ffmpeg
  pillow numpy xatlas plyfile`, and **nvdiffrast**.
- Weights: `TencentARC/InstantMesh` (the customized Zero123++ UNet + the LRM checkpoint).

## Working install recipe (anticipated — adapt from the run)
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

## Anticipated issues (to confirm/fill on the run)
| Likely symptom | Likely cause | Likely fix |
|---|---|---|
| `ModuleNotFoundError: nvdiffrast` | needed by FlexiCubes mesh extraction | `pip install --no-build-isolation git+…/nvdiffrast.git` |
| `diffusers` custom_pipeline error for Zero123++ | newer diffusers removed the `custom_pipeline` string | pin `diffusers==0.27.2` (already pinned) or ship a local `zero123plus.py` |
| OBJ→GLB texture loss | `run.py` writes OBJ + texmap | convert with trimesh; for scoring, geometry is enough |
| pinned-version conflicts with base torch | the 4.40/0.27.2 pins may want a specific torch | keep base torch; install with `--no-deps` if it tries to downgrade |

## Verdict for the paper
Apache-2.0 (cleaner than SAM 3D's custom license) but **needs nvdiffrast** like TRELLIS. The Zero123++
stage is stochastic (seed-dependent). Expect the "thin-structure" weakness (FlexiCubes). Scores TBD.
