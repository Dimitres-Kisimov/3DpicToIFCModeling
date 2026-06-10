# SAM 3D Objects Integration — Setup, State, and Open Issues

**Branch:** `sam3d-integration-wip` (forked off `mvp-retrieval-pipeline-phase1`)
**Status:** Work-in-progress. Inference NOT YET WORKING.
**Reason paused:** `pytorch3d` has no Windows pip wheel for Python 3.12 + torch 2.12; building from source requires Visual Studio + CUDA toolkit (multi-hour install with uncertain success rate on Windows).

This document captures everything that was done, what works, what doesn't, and exactly how to resume.

---

## 1. Why this branch exists

SAM 3D Objects is Meta's state-of-the-art single-image-to-3D model, released 2025-11-19 under the **SAM License** — fully commercial-safe for SCS (no royalties, no caps, no geographic exclusions, no MAU limits). Output is licensed for SCS to redistribute in IFC files.

Pairing SAM 3D Objects as a generative fallback with the 200-mesh ABO retrieval primary path would handle 100% of office furniture upload requests — retrieval for in-catalog items, generative reconstruction for the long tail.

The integration ran into Windows Python wheel availability problems that are real but not unsolvable. This branch preserves the in-progress work so it can be resumed when (a) pytorch3d ships a Windows + Python 3.12 + torch 2.12 wheel, (b) the SCS engineer is willing to invest 4–8 hours in source builds, or (c) SAM 3D Objects gets a stripped-down inference variant.

---

## 2. What's in this commit

| File | Purpose |
|---|---|
| `backend/python-scripts/run_sam3d.py` | The adapter that the main pipeline would call to invoke SAM 3D Objects on a single image |
| `backend/python-scripts/_kaolin_stub.py` | Minimal stub for the `kaolin` package (Meta's inference path imports kaolin for visualization + a tensor-shape assertion; real kaolin has a DLL-load issue on Windows + torch 2.12) |
| `SAM3D_SETUP.md` | This file |
| `.gitignore` | Adds `backend/sam3d/sam-3d-objects/` (Meta's repo clone, kept out of our repo) |

What is NOT in this commit but is needed at runtime:
- The Meta `sam-3d-objects` clone (~400 files, separate `.git`) — clone manually per §4
- ~13.8 GB of SAM 3D Objects weights — downloaded automatically per §4 once HF auth is set up
- A Python 3.12 environment with the dep stack from §5

---

## 3. Why a second Python interpreter (3.12) is needed

The main SCS pipeline runs on Python 3.13. SAM 3D Objects' dependency stack does not work on 3.13:

- `kaolin` (NVIDIA's 3D library) — no Windows wheels for 3.13 yet, latest officially targets 3.8–3.11
- `open3d` — top officially-supported version is 3.12
- `pytorch3d` — only source build on Windows even for 3.12

Python 3.12 is already installed on this machine (`py -3.12`) so the strategy is to keep 3.13 as the main interpreter and have `run_sam3d.py` spawned via 3.12 as a subprocess. The adapter does this; the bridge in `apiRoutes.js`/`pythonBridge.js` needs to switch Python paths when invoking it (TODO at runtime — see §7).

---

## 4. How to set up SAM 3D Objects from scratch on Windows

### 4.1 Prerequisites

- Python 3.12 installed (`py -3.12 --version` should return `Python 3.12.x`). If not, get it from python.org.
- Python 3.13 installed (the main SCS interpreter).
- HuggingFace account approved for `facebook/sam-3d-objects` (gated — request access at https://huggingface.co/facebook/sam-3d-objects).
- HF access token saved to `~/.cache/huggingface/token` (one-time `huggingface-cli login`).
- ~15 GB of free disk space.

### 4.2 Clone Meta's official repo

```powershell
cd "c:\Users\dinos\Downloads\3DpicToIFCModeling"
mkdir backend\sam3d -ErrorAction SilentlyContinue
cd backend\sam3d
git clone --depth 1 https://github.com/facebookresearch/sam-3d-objects.git
```

### 4.3 Install dependencies into Python 3.12

```powershell
$PY312 = "C:\Users\dinos\AppData\Local\Programs\Python\Python312\python.exe"

# Core ML stack matching the main pipeline
& $PY312 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
& $PY312 -m pip install transformers accelerate bitsandbytes huggingface_hub `
                       hydra-core==1.3.2 rootutils easydict einops einops_exts `
                       timm xformers safetensors pillow numpy trimesh scipy `
                       omegaconf seaborn matplotlib gradio tqdm loguru rembg

# Windows-friendly wheels
& $PY312 -m pip install open3d                        # Open3D, works on 3.12
& $PY312 -m pip install spconv-cu126                  # Sparse 3D convs
& $PY312 -m pip install "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b"

# Windows wheels that DO NOT WORK out of the box (open issues — see §6):
#   kaolin    — DLL load failure on torch 2.12+cu126; stubbed via _kaolin_stub.py
#   pytorch3d — no Windows pip wheel for our torch version; must build from source
```

### 4.4 Download SAM 3D Objects weights

```powershell
& $PY312 -c "from huggingface_hub import snapshot_download; print(snapshot_download(repo_id='facebook/sam-3d-objects'))"
```

Caches ~13.8 GB into `~\.cache\huggingface\hub\models--facebook--sam-3d-objects\`. Notable files:
- `ss_generator.ckpt` — 6.4 GB (biggest diffusion model)
- `slat_generator.ckpt` — 4.7 GB
- `slat_decoder_mesh.ckpt` — 347 MB (the one we want — skips Gaussian splat decoders)
- Encoders / smaller decoders ~100–200 MB each

### 4.5 Smoke-test the imports

```powershell
& $PY312 -c "
import sys
sys.path.insert(0, r'c:\Users\dinos\Downloads\3DpicToIFCModeling\backend\python-scripts')
import _kaolin_stub; _kaolin_stub.install()
sys.path.insert(0, r'c:\Users\dinos\Downloads\3DpicToIFCModeling\backend\sam3d\sam-3d-objects')
sys.path.insert(0, r'c:\Users\dinos\Downloads\3DpicToIFCModeling\backend\sam3d\sam-3d-objects\notebook')
import os
os.environ.setdefault('CONDA_PREFIX', '')
os.environ.setdefault('LIDRA_SKIP_INIT', 'true')
from sam3d_objects.pipeline.inference_pipeline_pointmap import InferencePipelinePointMap
print('OK')
"
```

Without pytorch3d, this currently fails with `ModuleNotFoundError: No module named 'pytorch3d'`. That's the open blocker.

---

## 5. What works and what doesn't (state at this commit)

| Component | State | Notes |
|---|---|---|
| HF auth + gated-repo access | ✅ working | `dimikissimov` has both SAM 3 and SAM 3D Objects ACCEPTED |
| Weights download | ✅ complete | 13.82 GB on disk, all critical .ckpt files present |
| Meta repo clone | ✅ complete | `backend/sam3d/sam-3d-objects/` |
| Python 3.12 installed | ✅ | `py -3.12 --version` → 3.12.2 |
| torch + cu126 on 3.12 | ✅ | `torch 2.12.0+cu126`, `cuda True` |
| transformers, accelerate, bitsandbytes on 3.12 | ✅ | |
| MoGe (depth model) | ✅ | `pip install` from git ref worked |
| spconv-cu126 (sparse 3D convs) | ✅ | |
| open3d on 3.12 | ✅ | 0.19.0 |
| seaborn, matplotlib, gradio | ✅ | |
| **kaolin** | ⚠️ stubbed | Real kaolin has DLL load error on torch 2.12+cu126. The 4 things it's used for (`IpyTurntableVisualizer`, `Camera`, `CameraExtrinsics`, `PinholeIntrinsics`, `check_tensor`) are not on the inference forward path — stubbed in `_kaolin_stub.py`. Real install would resolve cleanly with `--find-links https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html` IF we downgraded to torch 2.5.1 cu121, which would break the main pipeline. |
| **pytorch3d** | ❌ blocking | `InferencePipelinePointMap` imports `look_at_view_transform` + `Transform3d`. No Windows wheel for Python 3.12 + torch 2.12. Source build requires Visual Studio 2022, CUDA toolkit 12.6, ~30 min compile time, often fails on Windows. |
| `sam3d_objects` package install (`pip install -e .`) | ❌ deps cascade | Meta's `pyproject.toml` requires training infra: `auto-gptq` (needs torch at build time), `mosaicml-streaming`, `sagemaker`, `bpy` (Blender), `pyrender`. Workaround: skip `pip install` and add `backend/sam3d/sam-3d-objects/` to `sys.path` at runtime (the adapter does this). |
| Adapter `run_sam3d.py` | ✅ written, untested | Spawns 3.12 subprocess, installs kaolin stub, imports `Inference`, runs on input image, exports GLB. Will fail at the pytorch3d import until §6 is resolved. |

---

## 6. Open issues / how to unblock

### 6.1 pytorch3d on Windows (the only hard blocker)

The cleanest path forward is one of:

1. **Wait for a Windows wheel** — pytorch3d does occasionally ship binary wheels via the `nvcrt` channel. Check https://github.com/facebookresearch/pytorch3d/issues for `windows+wheels` updates.
2. **Build from source** — see `setup.md` in the cloned `sam-3d-objects` repo. Requires Visual Studio 2022 + CUDA toolkit 12.6 + matching MSVC. ~30 min compile, ~50% success rate on Windows in community reports.
3. **Stub the used parts** — only `look_at_view_transform` and `Transform3d` are imported by `InferencePipelinePointMap`. Both are math-only (no compiled extensions); could be reimplemented in pure torch in ~50 LOC. Risk: more pytorch3d functions might be imported deeper in `sam3d_objects`'s internal modules.
4. **Move to Linux** — if SCS gets a Linux box (WSL2 included), `pip install pytorch3d` works directly.

### 6.2 Path overrides in the Node bridge

`apiRoutes.js` currently uses `config.PYTHON_PATH` (which points to Python 3.13). When invoking `run_sam3d.py` it needs to switch to `py -3.12` or an explicit `C:\Users\dinos\AppData\Local\Programs\Python\Python312\python.exe`. Add a `SAM3D_PYTHON_PATH` env var.

### 6.3 VRAM verification

When the import wall is cleared, the first real test is whether inference fits in 8 GB VRAM with FP16 + accelerate offload. Expected:
- `ss_generator` peak ~5–7 GB at FP16
- `slat_generator` peak ~4–6 GB at FP16
- `slat_decoder_mesh` ~2 GB

With `device_map="auto"` + 64 GB system RAM CPU offload, all stages should fit but inference will be slow: 60–180 s per image.

---

## 7. To resume this work

1. Switch to this branch: `git checkout sam3d-integration-wip`
2. Re-clone Meta's repo (it's gitignored): `cd backend/sam3d && git clone --depth 1 https://github.com/facebookresearch/sam-3d-objects.git`
3. Re-install Python 3.12 deps per §4.3
4. Re-download weights per §4.4 (will be cached if you already did this)
5. Resolve the pytorch3d blocker per §6.1
6. Run `py -3.12 backend/python-scripts/run_sam3d.py <input.jpg> <output.glb>` to smoke-test
7. If it works, modify `apiRoutes.js` to invoke SAM 3D as the generative fallback when retrieval similarity < threshold

---

## 8. Final note on commercial safety

This branch's licence story is unchanged from `mvp-retrieval-pipeline-phase1`:
- All SCS code: MIT (yours)
- ABO meshes: CC-BY-4.0 (attribution in IFC Pset and frontend credits)
- SAM 3D Objects weights: SAM License (commercial-safe — no royalties, no caps, no geographic exclusion)
- All Python deps used at runtime: Apache-2.0 / MIT / BSD

The blocker is purely engineering effort on Windows. Nothing here changes the legal posture documented in `TECHNICAL_REPORT_SCS.md` §6.4.
