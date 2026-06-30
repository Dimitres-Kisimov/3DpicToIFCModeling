# Manual: SAM 3D Objects (Meta) — 🟡 installed, kaolin ABI blocker

**Status:** Repo cloned, **13.8 GB gated weights downloaded successfully** (the big win — this model
**never ran on the original Windows box** because of `pytorch3d`; on Linux that wall is gone), the
`CONDA_PREFIX` crash fixed, but inference is blocked on a **`kaolin` ABI mismatch** (real `kaolin` ops
are imported, built against a different torch). License: **SAM License** (custom, commercial-OK);
**dataset SA-3DAO is CC-BY-NC**. **Needs ≥32 GB VRAM.**

## The single biggest unlock
SAM 3D's `SAM3D_SETUP.md` (project branch `sam3d-integration-wip`) says verbatim:
*"Move to Linux → `pip install pytorch3d` works directly."* **We're on Linux.** The two Windows
blockers (`pytorch3d` no wheel, `kaolin` DLL) that paused this for the whole project simply don't apply.

## Requirements
- torch (the venv resolved to **2.12.1+cu130** via SAM 3D's deps — kept internally consistent), **≥32 GB VRAM**.
- **HuggingFace token** + accepted gate at https://huggingface.co/facebook/sam-3d-objects (model is gated).
- Repo: `https://github.com/facebookresearch/sam-3d-objects` → `/workspace/repos/SAM3D`
- Real entrypoint (recovered from the project's branch): **`from inference import Inference`** in `notebook/`.

## Working install recipe (from the branch's SAM3D_SETUP.md — do NOT `pip install -e .`)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
export HUGGING_FACE_HUB_TOKEN=hf_xxx HF_TOKEN=hf_xxx     # your read token, gate accepted
python -m venv /workspace/envs/sam3d --system-site-packages
source /workspace/envs/sam3d/bin/activate
git clone --depth 1 https://github.com/facebookresearch/sam-3d-objects /workspace/repos/SAM3D
# NOTE: `pip install -e .` cascades into training infra (auto-gptq, mosaicml, sagemaker, bpy) — skip it,
# add the repo to sys.path at runtime instead.
pip install -q transformers accelerate huggingface_hub hydra-core==1.3.2 rootutils easydict einops \
    einops_exts timm xformers safetensors pillow numpy trimesh scipy omegaconf tqdm loguru rembg \
    onnxruntime opencv-python-headless seaborn matplotlib gradio
pip install -q open3d
pip install -q "git+https://github.com/microsoft/MoGe.git"
pip install --no-build-isolation "git+https://github.com/facebookresearch/pytorch3d.git@stable"  # Linux: builds fine
python -c "from huggingface_hub import snapshot_download; snapshot_download('facebook/sam-3d-objects')"
```

## Run (real entrypoint from the project branch)
```python
import os, sys
os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")   # Meta's code does CUDA_HOME = CONDA_PREFIX
sys.path.insert(0, "/workspace/repos/SAM3D"); sys.path.insert(0, "/workspace/repos/SAM3D/notebook")
from inference import Inference                            # notebook/inference.py
inf = Inference(".../checkpoints/pipeline.yaml", compile=False)
out = inf(rgba_image, mask, seed=42)                       # mask from rembg alpha
out["mesh"].export("x.glb")
```

## Issues I hit and the fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | gated 403 on weight download | model is gated by Meta | accept the license on the HF model page + `export HUGGING_FACE_HUB_TOKEN=hf_…` (validated with `HfApi().model_info(...)` first → 31 files = OK) |
| 2 | `KeyError: 'CONDA_PREFIX'` at `from inference import Inference` | Meta's `notebook/inference.py` does `os.environ["CUDA_HOME"] = os.environ["CONDA_PREFIX"]`, which crashes under a venv (no conda) | `os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")` before the import |
| 3 | `ModuleNotFoundError: seaborn` (then matplotlib, gradio) | viz deps not installed | `pip install seaborn matplotlib gradio` |
| 4 | `kaolin/_C.so: undefined symbol: …c10_cuda…` | **OPEN** — installed `kaolin` built against a different torch than the venv's 2.12.1+cu130 | **TODO:** either compile kaolin from source against torch 2.12.1 (nvcc available), or stub the specific `kaolin.ops.spc` ops the inference path uses (the branch claims they're not forward-path — verify) |

## Verdict for the paper
The most *capable* model on cluttered real photos (≥5:1 human-preference win in the paper), and the
**only place it can run for SCS is Linux** — confirming the Windows wall was the real blocker, not the
model. Remaining work is the kaolin ABI fix. Custom SAM License + NC dataset = most legal attention needed.
