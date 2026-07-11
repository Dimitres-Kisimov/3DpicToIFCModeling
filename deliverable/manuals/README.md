# Single-Image→3D Model Reproduction Manuals

**Living document** — updated after *each* model is tested on the cloud GPU. Each model has its own
manual with: hardware/requirements, the **exact working install recipe**, the **issues actually hit
and how they were fixed**, run commands, and status. This is the honest deployment reality, not the
README-promised happy path.

**Test environment:** RunPod **H200 (143 GB)**, template *RunPod PyTorch 2.8.0*, **torch 2.8.0+cu128,
CUDA 12.8**, 120 GB disk, Ubuntu, 160 vCPU. (An A100 80 GB works for all of these too.)

## Status board (updated 2026-07-01)

| # | Model | License | Status | Mean F@0.02 | Manual |
|---|---|---|---|---|---|
| 1 | **TripoSG** | MIT | ✅ **WORKS** — 10/10 meshes | **0.393** | [TripoSG.md](TripoSG.md) |
| 2 | **SAM 3D Objects** | SAM License | ✅ **WORKS** — 10/10 meshes (sdpa backend) | **0.368** | [SAM3D.md](SAM3D.md) |
| 3 | **TRELLIS-image-large** | MIT | ✅ **WORKS** — 10/10 meshes (mesh-only) | **0.347** | [TRELLIS.md](TRELLIS.md) |
| 4 | **InstantMesh** | Apache-2.0 | ✅ **WORKS** — 10/10 meshes | **0.328** | [InstantMesh.md](InstantMesh.md) |
| 5 | **TRELLIS.2-4B** | MIT | ⏳ deferred (separate repo) | tbd | [TRELLIS2.md](TRELLIS2.md) |
| — | TripoSR | MIT | ✅ baseline (run locally) | 0.278/0.295 | (see investigation report) |

**4 of 5 cloud generators working** (all but the deferred TRELLIS.2). Generator ranking:
**TripoSG > SAM 3D > TRELLIS > InstantMesh > TripoSR.**

Reference baselines for the same 10 furniture types: **TripoSR·SAM2 = 0.278, TripoSR·rembg = 0.295,
ABO ground truth = 1.00.**

## Next-wave candidates (Stage-7 licence audit, 2026-07-11) — 🟡 DRAFT manuals, not yet pod-proven

The second licence audit ([docs/HUGGINGFACE_MODEL_NARROWING.md](../../docs/HUGGINGFACE_MODEL_NARROWING.md),
Stage 7) cleared these royalty-free, EU-safe models for a future pod run. Each has a **draft** manual
(written from repo README/LICENSE/HF-API research, 2026-07-11 — recipes are *anticipated*, not proven):

| Model | Org | Licence (code / weights) | VRAM | Textured? | Manual |
|---|---|---|---|---|---|
| **Direct3D-S2** | DreamTechAI | MIT / MIT | 10 GB @512³, ~24 GB @1024³ | no | [DIRECT3D_S2.md](DIRECT3D_S2.md) |
| **Step1X-3D** | StepFun | Apache-2.0 / Apache-2.0 | 27–29 GB (with texture) | **yes** | [STEP1X_3D.md](STEP1X_3D.md) |
| **Hi3DGen** (repo: Stable3DGen) | Stable-X | MIT / MIT + Apache-2.0 | not stated (~16 GB est., TRELLIS lineage) | no | [HI3DGEN.md](HI3DGEN.md) |
| **PartCrafter** | wgsxm (PKU/CMU) | MIT / MIT | ≥8 GB | no (part-level!) | [PARTCRAFTER.md](PARTCRAFTER.md) |
| MIDI-3D *(optional)* | VAST-AI | Apache-2.0 / Apache-2.0 | ~30 GB (textured scene) | optional | [MIDI3D.md](MIDI3D.md) |
| Unique3D *(optional)* | AiuniAI | MIT / weights unpinned (no HF repo id) | not recorded | yes | [UNIQUE3D.md](UNIQUE3D.md) |

Draft infer scripts for the four queued models exist in `cloud_bundle/` (`infer_direct3ds2.py`,
`infer_step1x3d.py`, `infer_hi3dgen.py`, `infer_partcrafter.py`) plus matching `install_models.sh`
entries (`bash install_models.sh nextwave`). All marked DRAFT until the first `.glb` lands.

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
6. **A compiled-attention dep (`flash_attn`) with the wrong-torch wheel fails as `ModuleNotFoundError`,
   not an obvious ABI error.** `import flash_attn` → `undefined symbol: _ZN3c10…` (a `c10`/torch symbol)
   means the prebuilt `.so` was built for a *different* torch. **Don't fight it** — most of these models
   (TRELLIS lineage, SAM 3D) have an **`sdpa` attention backend** (pure-PyTorch `scaled_dot_product_
   attention`, identical math, no compiled dep). Force it (`ATTN=sdpa`) and skip flash_attn entirely.
7. **`pkill -f <scriptname>` from your launch command kills the launching shell.** If your SSH command
   is `pkill -f infer_x; nohup python infer_x.py &`, the pkill pattern matches its *own* shell's command
   line and kills it before `nohup` runs — the relaunch silently does nothing. Check `ps` first; only
   kill by a pattern that can't match the launcher (or don't kill if nothing is running).

**Meta-lesson:** every "model loads" ≠ "model produces a mesh." Loading and the final GLB-export step
fail on *different* missing deps — test all the way to a written `.glb`. (SAM 3D alone needed **12
distinct fixes** between "imports" and "writes a GLB" — see [SAM3D.md](SAM3D.md).)

## Turning generated meshes into an IFC/BIM catalog — two hard caveats

`cloud/build_ifc_catalog.py` exports the generated meshes as a validated IFC4 furniture catalog
(`IFC4_BIM_CATALOG_OK`). Two caveats are baked in, and both are **non-negotiable for real BIM use**:

1. **Decimation is mandatory (handled automatically).** Raw generator output is **150 k – 2.7 M faces**
   per item → a 10-item catalog would be **hundreds of MB** and Revit chokes. The tool decimates each
   item to ~8 k faces (quadric), giving a **~2.4 MB** IFC4 for all 10. *Never* feed raw meshes to IFC.
   *(This is the same lesson as Finding B in CLOUD_BENCHMARK_FINDINGS.md.)*

2. **Orientation + real-world scale is BEST-EFFORT, not exact (Finding A).** Generators emit meshes in
   **inconsistent canonical frames** — even the ABO ground truth isn't uniformly oriented. The tool
   normalizes to **Z-up** (IFC convention) and scales each item so its **height matches a typical real
   furniture dimension in metres** (chair 0.90 m, table 0.75 m, bookshelf 1.90 m, …). This lands **most
   items** at sensible sizes, but **fails for pieces where height isn't the defining dimension** or that
   are mis-oriented — e.g. a generated **bed came out 0.70×0.74×0.55 m** (footprint far too small,
   because its long axis mapped onto the vertical). **Always sanity-check the printed `X×Y×Z m` dims;
   outliers need a manual per-item orientation/scale nudge.** A fully-automatic fix would require per-item
   up-axis detection (PCA/ICP-to-a-canonical-reference) — not yet implemented.

**Rule of thumb:** `generated mesh → decimate ≤8 k → Z-up → scale to real metres → IFC4`, then **eyeball
the dimensions** before trusting the catalog in a real room model.
