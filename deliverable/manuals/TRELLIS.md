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

## A100 campaign addendum — issues #10–#14 (2026-07-11→12 campaign)

The A100 campaign re-proved TRELLIS from a fresh pod (r10 + 187-item sweep; 197 TRL items in the final
IFC-gated catalog) and hit five blockers the H200 run never saw. The env that finally worked:
**torch 2.5.1+cu121** (NOT the pod's torch 2.13/cu130 base — see #12), `xformers==0.0.28.post3`,
**real kaolin 0.18.0** (the #5 stub is fine for TRELLIS alone, but the shared A100 stack installed the
full wheel), `ATTN_BACKEND=sdpa` for dense + `SPARSE_ATTN_BACKEND=xformers` for sparse attention.

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 10 | `from_pretrained("microsoft/TRELLIS-image-large")` dies with a hub **404 on `ckpts/...`** | TRELLIS wraps the real loading error in a **bare `except`** and falls through to hub resolution, so the pipeline's **relative ckpt paths** (`ckpts/…`) get resolved as repo ids by newer `huggingface_hub` — the 404 is a red herring | `snapshot_download(model_id)` first, then `from_pretrained(<local dir>)` — same class as the TripoSG `15fce17` fix (commits 39543ff, da0217e). *verified 2026-07-12 (A100)* |
| 11 | `SLatGaussianDecoder` fails wanting `flash_attn` even with `ATTN_BACKEND=sdpa` set | the **sparse** attention module reads its **own** `SPARSE_ATTN_BACKEND` env var and supports **only `xformers` \| `flash_attn`** — v1's sparse module has **no sdpa path**, so a dense-only pin still leaves a flash_attn import in the gaussian-decoder path (and TRELLIS's bare except turned the real error into the misleading #10 404) | `SPARSE_ATTN_BACKEND=xformers` + **`xformers==0.0.28.post3` from the cu121 index** (the torch-2.5.1-matched build); keep `ATTN_BACKEND=sdpa` for dense (85fd61c). *verified 2026-07-12 (A100)* |
| 12 | kaolin install "succeeds" but `import kaolin` fails — either an ancient 0.1 package or `undefined symbol: c10_cuda_check_implementation` | **kaolin has NO wheel for torch 2.13/cu130.** A plain `pip install kaolin` grabs the broken PyPI kaolin 0.1 source package, or an ABI-mismatched wheel — the undefined-c10-symbol error means the wheel came from the wrong source | pin the env to **torch 2.5.1+cu121** and install `kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html` (the NVIDIA find-links index); **always verify with an actual `import kaolin`** (fix_round3.sh, night_shift2.sh). *verified 2026-07-12 (A100)* |
| 13 | `to_glb` needs `diff_gaussian_rasterization` — which is **Inria non-commercial** | #9 again, but now a **licence decision**, not a convenience call: the texture bake's rasterizer is excluded per the Stage-8 licence audit | **geometry-only GLB export is the licence-clean path** — export `r["mesh"][0]` directly (e8690ec, infer_trellis.py); the scorer is geometry-only, so results are scorer-equivalent to the textured H200 run. *verified 2026-07-12 (A100)* |
| 14 | utils3d API drift (again) on the fresh env | any "latest" utils3d breaks TRELLIS — the H200 lesson (#8) holds unchanged on the new stack | utils3d **MUST** be the pinned commit `9a4eb15e4021b67b12c460c7057d642626897ec8`, every rebuild, no exceptions. *verified 2026-07-12 (A100)* |

## Verdict for the paper
Most-downloaded open-source model (1.1 M), MIT — but the **highest integration cost** by far, and it
**depends on nvdiffrast (NVIDIA license)**, so it's a commercial flag. Strong quality expected; scores TBD.
