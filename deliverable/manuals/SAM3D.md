# Manual: SAM 3D Objects (Meta) — ✅ WORKING (5th generator, F=0.368, 2nd overall)

**Status:** **Fully working on the H200.** 10/10 furniture meshes generated, scored **0.368 mean F@0.02**
(2nd of 5 generators, behind only TripoSG 0.393). Avg **8.7 s/image** (fastest measured). The model that
**never ran on the original Windows box** (no `pytorch3d`/`kaolin` wheels) runs cleanly on Linux.
License: **SAM License** (custom, commercial-OK); **dataset SA-3DAO is CC-BY-NC** (most legal care needed).
**Re-proven end-to-end on the 2026-07-11→12 A100 campaign** after a full from-zero env rebuild (r10
10/10 into the final catalog) — that rebuild added fixes **#13–#17** below, including a numpy resolution
that **supersedes #8** on the A100/kaolin-0.18 stack.

## The one thing that mattered: use the `sdpa` attention backend, not flash_attn
SAM 3D's `inference_pipeline.py` **force-sets `ATTN_BACKEND=flash_attn` at module load.** Its published
`flash_attn` dependency has **no prebuilt wheel matched to the torch 2.5.1 base**, so the `.so` fails with
an undefined-`c10`-symbol **ABI error** that surfaces misleadingly as `ModuleNotFoundError: No module
named 'flash_attn'`. The model's sparse-attention module (TRELLIS-derived `tdfy_dit`) has a fully
**exact-equivalent `sdpa` backend** (pure PyTorch `scaled_dot_product_attention`, identical math, **no
compiled dependency**). Pinning `ATTN=sdpa` sidesteps the entire flash_attn rabbit hole. **SAM 3D is not
broken** — people run it fine *with* flash_attn on matched-torch setups; this was purely env-matching.

## Requirements (Meta's official env — the coherent one)
- **torch 2.5.1+cu121** (the official base; cu121 runs fine on a cu124 driver — backward compatible). ≥32 GB VRAM.
- **HuggingFace token** + accepted gate at https://huggingface.co/facebook/sam-3d-objects (model is gated, 13.8 GB).
- Repo: `https://github.com/facebookresearch/sam-3d-objects` → `/workspace/repos/SAM3D`
- Entrypoint: **`from inference import Inference`** in `notebook/`.

## Working install recipe
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
export HUGGING_FACE_HUB_TOKEN=hf_xxx HF_TOKEN=hf_xxx          # read token, gate accepted
python -m venv /workspace/envs/sam3d2 && source /workspace/envs/sam3d2/bin/activate
git clone --depth 1 https://github.com/facebookresearch/sam-3d-objects /workspace/repos/SAM3D

# 1) Official torch base first
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
# CAUTION (fix #13): requirements.p3d.txt is a GIT-SOURCE build of pytorch3d, NOT prebuilt wheels —
# install it with --no-build-isolation and TORCH_CUDA_ARCH_LIST set, BEFORE the inference reqs:
pip install --no-build-isolation -r /workspace/repos/SAM3D/requirements.p3d.txt
# CAUTION (fix #13): install the inference reqs PER-LINE with soft-fail — one bad line otherwise
# aborts the whole file (sam3d_final.sh does exactly this):
pip install -r /workspace/repos/SAM3D/requirements.inference.txt     # installs spconv-cu121, timm, etc.
# CAUTION (fix #16): re-check torch after ANY batch install — generic installs silently bump it.

# 2) flash_attn: the requirements wheel is ABI-WRONG. We DON'T need it (see sdpa below), but if you ever
#    do, install the torch-2.5-matched wheel (cxx11abiFALSE for the pytorch.org build):
pip install "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.5cxx11abiFALSE-cp312-cp312-linux_x86_64.whl"

# 3) Pure-python deps the partial install skips (install one batch; pin numpy each time — see numpy war):
pip install loguru timm==0.9.16 spconv-cu121==2.3.8 open3d trimesh optree==0.14.1 astor rootutils \
    randomname opencv-python==4.9.0.80 roma==1.5.1 einops xatlas==0.0.9 Rtree==1.3.0 omegaconf \
    "scikit-image==0.23.1" "tifffile==2024.8.30" "plyfile==1.0.3" "lightning==2.3.3" pyvista \
    "pymeshfix==0.17.0" igraph "numpy==1.26.4"
pip install "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b"

# 4) THE FIX: pin sdpa so flash_attn is never imported (exact-equivalent, no compiled dep)
F=/workspace/repos/SAM3D/sam3d_objects/model/backbone/tdfy_dit/modules/sparse/__init__.py
# after the `__from_env()` call, append:  ATTN = "sdpa"
python -c "import huggingface_hub as h; h.snapshot_download('facebook/sam-3d-objects')"
```

## Run (real entrypoint) — pass NUMPY image + mask, not PIL
```python
import os, sys, numpy as np
from PIL import Image
os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")     # Meta's code does CUDA_HOME = CONDA_PREFIX
os.environ.setdefault("LIDRA_SKIP_INIT", "true")
os.environ["SPARSE_ATTN_BACKEND"] = "sdpa"; os.environ["ATTN_BACKEND"] = "sdpa"
sys.path.insert(0, "/workspace/repos/SAM3D"); sys.path.insert(0, "/workspace/repos/SAM3D/notebook")

# white-bg mask (avoids rembg/onnxruntime conflict with the numpy-1.26.4 pin):
img = Image.open(path).convert("RGB"); arr = np.array(img)
fg = (np.abs(arr.astype(int) - 255).sum(2) > 30).astype(np.uint8)   # (H,W) 0/1 — NUMPY, not PIL

from inference import Inference
inf = Inference(".../checkpoints/pipeline.yaml", compile=False)
out = inf(arr, fg, seed=42)                # arr=numpy RGB, fg=numpy 0/1 mask
mesh = out["mesh"][0]                       # out['mesh'] is a LIST (batch); element is a MeshExtractResult
import trimesh; trimesh.Trimesh(mesh.vertices.detach().cpu().numpy(),
                                mesh.faces.detach().cpu().numpy()).export("x.glb")
# out also has: ['glb'] (ready Trimesh), ['gaussian'], ['pointmap'], ['scale'/'rotation'/'translation'] (pose!)
```

## Issues I hit and the fixes (the full chain)

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | gated 403 on weights | model gated by Meta | accept license on HF page + `HUGGING_FACE_HUB_TOKEN` |
| 2 | `KeyError: 'CONDA_PREFIX'` at import | Meta does `CUDA_HOME = os.environ["CONDA_PREFIX"]`, crashes under venv | `os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")` |
| 3 | torch 2.12.1+cu130 → "CUDA driver too old" | a stray dep pulled cu130 torch; driver is cu124 | use Meta's **official torch 2.5.1+cu121** (cu121 runs on cu124 driver) — this also makes kaolin/pytorch3d/gsplat wheels coherent |
| 4 | `flash_attn_2_cuda.so: undefined symbol _ZN3c10…` | prebuilt flash_attn wheel built for a **different torch** (ABI mismatch); surfaces as `ModuleNotFoundError` | **don't use flash_attn** — pin `ATTN=sdpa` (exact-equivalent). (Or install the torch-2.5-matched wheel.) |
| 5 | run imports flash_attn even with `ATTN_BACKEND=sdpa` env | `inference_pipeline.py` **force-sets `ATTN_BACKEND=flash_attn` at module load**, overriding env | hard-pin `ATTN = "sdpa"` in `…/modules/sparse/__init__.py` right after `__from_env()` |
| 6 | every relaunch silently did nothing (stale log) | my `pkill -f infer_sam3d` matched the **launching shell itself** (its cmdline contained the script name) → killed its own shell before `nohup` | drop the pkill (nothing was running) / use a pattern that can't match the launcher |
| 7 | `ModuleNotFoundError` cascade: loguru, timm, spconv-cu121, open3d, trimesh, optree, astor, cv2, igraph, pyvista, pymeshfix, MoGe, plyfile | partial install skipped ~13 pure-python deps | install them (batch above); `point-cloud-utils` has no py3.12 wheel — **not on the inference path**, skip it |
| 8 | `kaolin requires numpy<2.0 but you have 2.5.0` (recurring) | scikit-image's **tifffile wants numpy≥2.1**; kaolin/spconv need **<2.0** | pin `numpy==1.26.4` + `tifffile==2024.8.30` + `plyfile==1.0.3` (the numpy-1.x-compatible versions); re-pin numpy after any install that bumps it |
| 9 | `cannot import name 'normals_edge' from utils3d.numpy` | SAM3D's `SceneVisualizer`/`image_mesh` imports 5 funcs the installed utils3d dropped — **viz-only, not on the mesh-decoder path** | shim `depth_edge, normals_edge, points_to_normals, image_uv, image_mesh` into `utils3d.numpy` before `from inference import Inference` |
| 10 | `'Image' object has no attribute 'astype'` | Meta's `merge_mask_to_rgba` does `image[...,:3]` + `mask.astype(...)` — wants **numpy**, I passed PIL | return `(numpy_rgb, numpy_0/1_mask)` from the mask helper |
| 11 | `'list' object has no attribute 'vertices'` | `out['mesh']` is a **LIST** (batch dim) of `MeshExtractResult`, not a single mesh | unwrap `out['mesh'][0]`; coerce torch `.vertices/.faces` → trimesh |
| 12 | local scorer `MemoryError` on 10th mesh | raw meshes are **130 k–1.06 M faces**; ten of them exhaust Windows RAM (py3.14) | **decimate to 150 k faces** (open3d quadric, vertex-colors preserved) before scoring/display |
| 13 | `pip install -r requirements.p3d.txt` dies with `No module named 'torch'` and **pip aborts the whole file** | `requirements.p3d.txt` is a **git-source build of pytorch3d**, NOT prebuilt wheels — under build isolation the build env has no torch, and one failing line kills every remaining line of the `-r` install | install it with **`--no-build-isolation` + `TORCH_CUDA_ARCH_LIST` set**; install `requirements.inference.txt` **per-line with soft-fail** so one bad line can't abort the rest (sam3d_final.sh). *verified 2026-07-12 (A100)* |
| 14 | `ModuleNotFoundError: hydra`, and `pip install hydra` doesn't fix it | the import name is `hydra`, but the PyPI package is **`hydra-core`** (plain `hydra` is an unrelated package) | `pip install hydra-core`. *verified 2026-07-12 (A100)* |
| 15 | `AttributeError`/`KeyError` on **`np.long`** from spconv's dtype table | spconv's dtype table wants `np.long` — a **numpy-2.x** symbol — while this manual's old `numpy==1.26.4` pin (fix #8) predates it | **`numpy==2.1.*` works with `kaolin==0.18.0`** — this **supersedes the 1.26.4 pin (#8)** on the A100 stack; sam3d_final.sh keeps a 1.26.4↔2.1 toggle and lets the import gate decide (night_shift.sh landed 2.1). *verified 2026-07-12 (A100)* |
| 16 | after a dependency-chase batch install, **every compiled wheel** (pytorch3d/kaolin/spconv) is suddenly ABI-broken | a generic `pip install X` during the chase **silently bumped torch 2.5.1 → 2.13**, orphaning every extension compiled against 2.5.1 | **re-pin torch after any batch install** (`pip install torch==2.5.1 torchvision==0.20.1 --index-url …/cu121`) and re-run the import gate before trusting the env. *verified 2026-07-12 (A100)* |
| 17 | a "successful" batch of 180 outputs — **every file identical** | the old infer script's **glob-fallback copied a repo asset when generation failed**, fabricating 180 identical outputs that looked like a completed run | **never write placeholder output on failure** — fail loudly and skip (infer_sam3d.py rewrite); 1-mesh >50 KB **preflight gates** + **distinct-file-size postchecks** are now standard for every engine (queue3_verified.sh). *verified 2026-07-12 (A100)* |

## Verdict for the paper
**2nd-best generator (0.368), fastest (8.7 s), and uniquely outputs pose (scale/rotation/translation)** —
directly useful for the object-placement half of the SCS pipeline. The Windows wall was the real blocker,
not the model; on Linux with the `sdpa` backend it is a strong, fast performer. Highest-poly output of all
(decimation mandatory). Custom SAM License + NC dataset = most legal attention of the five.
