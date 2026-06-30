# Manual: TRELLIS.2-4B (Microsoft) — ⏳ pending (separate repo)

**Status:** Not yet run. **It is NOT the same codebase as TRELLIS-v1** — different repo, different package
(`trellis2`), different representation (field-free **O-Voxel**, full PBR), different exporter (`o_voxel`).
My initial install wrongly reused the v1 repo (it can't load the .2-4B checkpoint). License MIT.
**Needs ≥24 GB VRAM**, CUDA 12.4+ (we have 12.8).

## Requirements
- torch matched to torchvision (apply the version-war fix from the TRELLIS-v1 manual #1), CUDA on PATH.
- Repo: **`https://github.com/microsoft/TRELLIS.2`** (NOT microsoft/TRELLIS) → `/workspace/repos/TRELLIS2`
- Package: `trellis2` + `o_voxel` (the exporter). Same compiled-extension family as v1 (nvdiffrast etc.).
- Weights: `microsoft/TRELLIS.2-4B` (~8–16 GB, the 4B model).

## Loading API (from the HF model card)
```python
import sys; sys.path.insert(0, "/workspace/repos/TRELLIS2")
from trellis2.pipelines import Trellis2ImageTo3DPipeline
pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipeline.cuda()
mesh = pipeline.run(image)[0]
import o_voxel
glb = o_voxel.postprocess.to_glb(...)        # <-- exact args: read the repo's example script
glb.export("sample.glb", extension_webp=True)
```

## Working install recipe (anticipated — fill from the run)
```bash
export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=9.0
python -m venv /workspace/envs/trellis2 --system-site-packages
source /workspace/envs/trellis2/bin/activate
git clone --recurse-submodules https://github.com/microsoft/TRELLIS.2 /workspace/repos/TRELLIS2
# follow its setup.sh; expect the SAME deps as v1: matched torch/xformers, spconv, nvdiffrast,
# diffoctreerast, utils3d (pinned!), transformers, open3d — plus the `o_voxel` package.
# Apply ALL the v1 lessons: --no-deps xformers, --no-build-isolation for CUDA exts, honor pinned commits.
python -c "from huggingface_hub import snapshot_download; snapshot_download('microsoft/TRELLIS.2-4B')"
```

## Anticipated issues (the v1 lessons almost certainly recur)
| Likely symptom | Fix (from TRELLIS-v1 manual) |
|---|---|
| `torchvision::nms does not exist` | remove venv torch, `--no-deps` xformers (#1) |
| missing transformers/open3d/utils3d/kaolin | install + stub kaolin check_tensor (#2–#5) |
| nvdiffrast/diffoctreerast won't build | `--no-build-isolation` + CUDA_HOME (#6,#7) |
| `utils3d` API attribute error | install the **pinned commit** from TRELLIS.2's setup (#8) |
| `o_voxel.postprocess.to_glb(...)` arg error | read the repo's `example_image.py` for the exact call; or mesh-only export the `pipeline.run()` result |
| needs `diff_gaussian_rasterization` | mesh-only export fallback (v1 #9) or install from mip-splatting submodule |

## Verdict for the paper
The newest, most-liked model (966 likes), MIT, full PBR + arbitrary topology. Highest integration cost
(separate repo + o_voxel + 4B weights). Treat as the stretch goal once the 4 simpler models are scored.
