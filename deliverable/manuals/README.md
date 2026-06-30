# Single-Image→3D Model Reproduction Manuals

**Living document** — updated after *each* model is tested on the cloud GPU. Each model has its own
manual with: hardware/requirements, the **exact working install recipe**, the **issues actually hit
and how they were fixed**, run commands, and status. This is the honest deployment reality, not the
README-promised happy path.

**Test environment:** RunPod **H200 (143 GB)**, template *RunPod PyTorch 2.8.0*, **torch 2.8.0+cu128,
CUDA 12.8**, 120 GB disk, Ubuntu, 160 vCPU. (An A100 80 GB works for all of these too.)

## Status board (updated 2026-06-30)

| # | Model | License | Status | Mean F@0.02 | Manual |
|---|---|---|---|---|---|
| 1 | **TripoSG** | MIT | ✅ **WORKS** — 10/10 meshes | **0.393** | [TripoSG.md](TripoSG.md) |
| 2 | **TRELLIS-image-large** | MIT | ✅ **WORKS** — 10/10 meshes (mesh-only) | **0.347** | [TRELLIS.md](TRELLIS.md) |
| 3 | **SAM 3D Objects** | SAM License | 🟡 deps fixed, loading model (flash_attn) | tbd | [SAM3D.md](SAM3D.md) |
| 4 | **InstantMesh** | Apache-2.0 | ✅ **WORKS** — 10/10 meshes | **0.328** | [InstantMesh.md](InstantMesh.md) |
| 5 | **TRELLIS.2-4B** | MIT | ⏳ pending (separate repo) | tbd | [TRELLIS2.md](TRELLIS2.md) |
| — | TripoSR | MIT | ✅ baseline (run locally) | 0.278/0.295 | (see investigation report) |

Reference baselines for the same 10 furniture types: **TripoSR·SAM2 = 0.278, TripoSR·rembg = 0.295,
ABO ground truth = 1.00.**

---

## Universal gotchas (hit *every* model — fix these first)

These five lessons recurred across all models. Internalize them and each manual gets shorter.

1. **`nvcc` exists but is NOT on PATH.** The CUDA 12.8 toolkit is at `/usr/local/cuda/bin/nvcc`, but
   the default shell can't find it → any compiled extension (`diso`, `nvdiffrast`, `diffoctreerast`,
   `kaolin`) fails to build. **Always first:**
   ```bash
   export PATH=/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
   ```
2. **Build isolation hides torch.** `pip install <cuda-ext>` builds in an isolated env that has **no
   torch**, so the build dies with `ModuleNotFoundError: No module named 'torch'`. **Fix:**
   `pip install --no-build-isolation <pkg>` (uses the venv's torch + your CUDA_HOME).
3. **The torch/torchvision version war.** Several deps (notably **`xformers`**) silently pull a
   *different* torch (e.g. 2.11/2.12) into the venv, which then mismatches the inherited
   `torchvision` → `RuntimeError: operator torchvision::nms does not exist`. **Fix:** keep ONE torch.
   Remove the venv-local torch so the base `2.8.0+cu128` shows through, then install the offender
   with `--no-deps`:
   ```bash
   pip uninstall -y torch torchaudio xformers
   pip install --no-deps xformers==0.0.32.post2   # the build matched to torch 2.8
   ```
4. **PEP 668 (externally-managed base python).** `pip install` into the system python refuses. Use a
   **venv** (`python -m venv env --system-site-packages`) per model, or `--break-system-packages` for
   throwaway checks only.
5. **`TORCH_CUDA_ARCH_LIST` must match the GPU.** H200 = **`9.0`** (Hopper sm_90); A100/A40 =
   `8.0;8.6`. Set it before compiling any extension or the kernels build for the wrong arch.

**Meta-lesson:** every "model loads" ≠ "model produces a mesh." Loading and the final GLB-export step
fail on *different* missing deps — test all the way to a written `.glb`.
