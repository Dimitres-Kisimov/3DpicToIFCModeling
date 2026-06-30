# Manual: TRELLIS-image-large (Microsoft) — ✅ WORKS

**Status:** ✅ **Working — 10/10 meshes, mean F@0.02 = 0.347** (2nd-best generator, behind TripoSG 0.393,
ahead of TripoSR 0.278/0.295). License MIT. **This was the hardest install of the set — 9 distinct
blockers**, mostly because TRELLIS's `setup.sh` pins exact versions/commits that a naive `pip install`
ignores. **Needs nvdiffrast** (NVIDIA Source Code License — research-use OK, commercial flag; see the risk
sheet). Best item: stool 0.99, bed 0.67; weak: bookshelf 0.16, table 0.18. We exported **mesh-only**
(skipped the Gaussian texture bake) — see issue #9.

## Requirements
- torch **2.8.0+cu128**, CUDA 12.8 on PATH, **≥16 GB VRAM**, `TORCH_CUDA_ARCH_LIST=9.0` (H200).
- Repo: `https://github.com/microsoft/TRELLIS` (`--recurse-submodules`) → `/workspace/repos/TRELLIS`
- Env vars at runtime: `ATTN_BACKEND=xformers SPCONV_ALGO=native` + the `trellis` package on `sys.path`.
- Compiled extensions: **nvdiffrast**, **diffoctreerast**, **spconv-cu118**, **xformers** (matched).
- Weights: `microsoft/TRELLIS-image-large` (~1.1 GB) + auto-downloads **DINOv2-L** (~1.1 GB) on first load.

## Working install recipe (the order matters)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=9.0
python -m venv /workspace/envs/trellis --system-site-packages
source /workspace/envs/trellis/bin/activate
git clone --recurse-submodules https://github.com/microsoft/TRELLIS /workspace/repos/TRELLIS
pip install -q pillow imageio imageio-ffmpeg trimesh numpy scipy easydict opencv-python-headless \
    tqdm einops omegaconf rembg onnxruntime transformers open3d igraph xatlas pyvista pymeshfix plyfile
# torch/xformers: install xformers WITHOUT letting it pull a new torch (see issue #1)
pip uninstall -y torch torchaudio xformers
pip install --no-deps xformers==0.0.32.post2
pip install spconv-cu118
# the EXACT utils3d commit TRELLIS pins (see issue #8) — NOT the latest
pip install "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8"
# compiled renderers (no-build-isolation so they see torch + CUDA_HOME)
pip install --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast.git"
pip install --no-build-isolation "git+https://github.com/JeffreyXiang/diffoctreerast.git"
# kaolin: only `check_tensor` is used (not forward-path) — stub it (see issue #5)
KS=/workspace/envs/trellis/lib/python3.12/site-packages/kaolin
mkdir -p $KS/utils; : > $KS/__init__.py; : > $KS/utils/__init__.py
echo "def check_tensor(*a, **k): return True" > $KS/utils/testing.py
```

## Run
```python
import os, sys; os.environ["ATTN_BACKEND"]="xformers"; os.environ["SPCONV_ALGO"]="native"
sys.path.insert(0, "/workspace/repos/TRELLIS")
from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils
p = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large"); p.cuda()
r = p.run(img, seed=42)
glb = postprocessing_utils.to_glb(r["gaussian"][0], r["mesh"][0], simplify=0.95, texture_size=1024)
glb.export("x.glb")
```

## Issues I hit (chronological) and the fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `RuntimeError: operator torchvision::nms does not exist` | `pip install xformers` pulled **torch 2.12.1** into the venv, shadowing base 2.8.0; torchvision (0.23, for 2.8) then mismatched | remove venv torch, `pip install --no-deps xformers==0.0.32.post2` so base torch 2.8 stays |
| 2 | `ModuleNotFoundError: transformers` | not in my install list (TRELLIS needs CLIP) | `pip install transformers` |
| 3 | `ModuleNotFoundError: open3d` | text-pipeline import in `trellis/pipelines/__init__.py` | `pip install open3d` |
| 4 | `ModuleNotFoundError: utils3d` | `|| true` in my script masked a failed install | `pip install git+…/utils3d.git` (then issue #8 pins the *right* commit) |
| 5 | `ModuleNotFoundError: kaolin` (then ABI error) | FlexiCubes imports `kaolin.utils.testing.check_tensor` — a debug assertion, **not forward-path** | **stub** just `check_tensor` (3-line fake module) — avoids compiling kaolin |
| 6 | `ModuleNotFoundError: nvdiffrast` (at *inference*, model loaded fine) | renderer needed only at mesh-extraction; my `pip install … || true` silently failed | `pip install --no-build-isolation git+…/nvdiffrast.git` (isolated build couldn't see torch) |
| 7 | nvdiffrast build `ERROR! Cannot compile … CUDA extension` | build isolation hid torch/CUDA | same `--no-build-isolation` + `PATH`/`CUDA_HOME` set |
| 8 | `AttributeError: module 'utils3d.torch' has no attribute 'perspective_from_fov_xy'` at `to_glb` | I installed **utils3d 1.7 (latest)**; TRELLIS pins an **older commit** where that function exists | install the exact pin from TRELLIS `setup.sh`: `utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8` |
| 9 | `ModuleNotFoundError: diff_gaussian_rasterization` at `to_glb` | the texture-bake step renders the Gaussian splat; that rasterizer is another pinned compiled ext (from mip-splatting submodule) | **mesh-only export fallback** — skip the gaussian texture bake and export `r["mesh"][0]` geometry directly (we score geometry; stills are grey anyway). Or install it from `mip-splatting/submodules/diff-gaussian-rasterization` |

**Headline lesson:** TRELLIS *loaded* successfully after issues #1–#5, but then **ran a full diffusion
pass and only failed at the final GLB export** (#6, #8). Always test to a written `.glb`, and **honor the
repo's pinned commit hashes** — "latest" breaks the API.

## Verdict for the paper
Most-downloaded open-source model (1.1 M), MIT — but the **highest integration cost** by far, and it
**depends on nvdiffrast (NVIDIA license)**, so it's a commercial flag. Strong quality expected; scores TBD.
