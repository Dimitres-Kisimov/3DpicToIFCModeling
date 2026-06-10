# Session Report — 3DpicToIFCModeling Setup & Research

**Date:** 2026-06-06
**Prepared for:** SCS (project owner)
**Machine:** Windows 11 Pro, RTX 4070 Laptop GPU (8 GB VRAM), 64 GB system RAM
**Project root:** [c:/Users/dinos/Downloads/3DpicToIFCModeling](c:/Users/dinos/Downloads/3DpicToIFCModeling/)

---

## 1. What was done

### 1.1 Environment setup
| Step | Result |
|---|---|
| Cloned `Dimitres-Kisimov/3DpicToIFCModeling` from GitHub | ✅ |
| Checked out branch `retrieval-pivot-blueprint` (HEAD `c78f3ac`) | ✅ |
| Verified all 9 remote branches — confirmed `retrieval-pivot-blueprint` is the latest line of work (nothing newer on any other branch) | ✅ |
| Read project docs: README.md, PROJECT_HISTORY.md, WORK_CHECKPOINT.md, PIVOT_BLUEPRINT.md, FULL_DOCUMENTATION.md | ✅ |
| Installed Node.js dependencies via `npm install` (242 packages) | ✅ |
| Installed PyTorch 2.12.0+cu126 (CUDA 12.6 wheels, ~2.6 GB) for Python 3.13 | ✅ |
| Installed ML/mesh/IFC libraries: transformers 5.10.2, ultralytics 8.4.60, rembg 2.0.76, trimesh 4.12.2, scikit-image 0.26.0, scipy 1.17.1, ifcopenshell 0.8.5, huggingface_hub 1.18.0 | ✅ |
| Created `.env` from `.env.example` | ✅ |
| Verified GPU detection: `torch.cuda.is_available() = True` | ✅ |
| Started Express server on http://localhost:3000 | ✅ |
| Verified `/api/health` → 200 OK | ✅ |
| Verified `/api/debug/health` → Python 3.13.3 + NumPy 2.4.4 + PyTorch 2.12.0+cu126 + CUDA True | ✅ |

### 1.2 Hardware identification — important correction
The original setup prompt said "RTX 4060 GTX". The actual GPU reported by `nvidia-smi` is **NVIDIA GeForce RTX 4070 Laptop GPU** (8 GB VRAM, driver 572.83, supports CUDA 12.8). The 8 GB VRAM figure was correct; the model name was not. All commands used the same `cu126` wheels and work identically; no change required.

### 1.3 Configuration decisions made

1. **`PYTHON_PATH` set to absolute path** (`C:/Users/dinos/AppData/Local/Programs/Python/Python313/python.exe`) in [.env](.env) — because plain `python` in PATH on this machine is the Windows Store stub, not Python 3.13.
2. **Used `npm.cmd` and `node backend/server.js` directly** instead of `npm start` — because PowerShell's default ExecutionPolicy blocks `.ps1` scripts including `npm.ps1`.
3. **Did not create a Python virtual environment** — followed the user's explicit instructions to install into Python 3.13 globally. Disk impact ~3.5 GB in pip cache plus site-packages.

---

## 2. The four hard problems we discussed

These are the **SCS failure modes** documented in [PIVOT_BLUEPRINT.md](PIVOT_BLUEPRINT.md) §1, which all subsequent research targets:

1. **Asymmetric legs** — single-view generative models have no symmetry prior; chair legs drift independently.
2. **Hallucinated back/underside** — single photo contains zero information about hidden surfaces; the model fills it in plausibly but wrong.
3. **Wrong colour and material** — no PBR fidelity; generated meshes get a flat per-vertex colour instead of textures + roughness + metalness.
4. **Wrong real-world dimensions** — no metric scale anywhere in the chain; the generated 3D box dimensions are arbitrary.

The 2026-05-21 pivot to **retrieval against a clean CAD library** ([PIVOT_BLUEPRINT.md](PIVOT_BLUEPRINT.md)) addresses all four by sidestepping single-view generation entirely for in-catalog items.

---

## 3. Research delivered in this session

### 3.1 SAM 3D licence verification
- Confirmed Meta's **SAM License** (verified directly from `facebook/sam3/LICENSE`) **grants commercial use, royalty-free, with no MAU cap, no revenue cap, and no geographic exclusion** for SAM 3, SAM 3D Objects, and SAM 3D Body.
- The prior AI's claim ("SAM 3 / SAM 3D not available") in [PROJECT_HISTORY.md:203](PROJECT_HISTORY.md#L203) was outdated; Meta released SAM 3 and SAM 3D on 2025-11-19, six months before that audit was written.
- **VRAM constraint:** SAM 3D Objects model card does not state a VRAM minimum. Community reports place native FP16 inference around **24 GB VRAM** — fits the secondary box, not this laptop. CPU offload via `accelerate` would run on this laptop but ~15× slower.
- **License obligations for SCS:** none for shipped IFC outputs. The SAM License binds only the model weights, not the generated meshes. Owner of generated meshes is SCS per the license text.

### 3.2 Three confirmed licence traps to AVOID
1. **`depth-anything/Depth-Anything-V2-Base-hf` and `-Large-hf`** = `cc-by-nc-4.0` (non-commercial). Only the **`Small`** variant is `apache-2.0`. The repo currently calls Small correctly — pin it.
2. **`tencent/Hunyuan3D-2`** Tencent Community License — verbatim from the LICENSE: *"DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"*, **1,000,000 MAU cap** (not 100M as the repo notes claimed), and explicit prohibition: *"You must not use the Tencent Hunyuan 3D 2.0 Works or any Output or results … to improve any other AI model"* — would block SCS from feeding Hunyuan3D outputs back into the retrieval index.
3. **`yolov8n-seg.pt` is `AGPL-3.0` and is committed at the repo root.** Even unused, distributing the binary in the source tree triggers AGPL obligations on surrounding code. **Recommended action: delete the file and replace with SAM 2.1 calls.**

### 3.3 Stable Fast 3D conditional
- `stabilityai/stable-fast-3d` is Stability Community License — free for organisations under **US$1,000,000 annual revenue**; enterprise license required above that.
- **Action needed:** SCS finance must confirm revenue position before adoption.
- Unique strength: **only surveyed model that explicitly emits PBR material parameters** (albedo, roughness, metalness).

### 3.4 Process model — three deployment paths discussed

| Path | When to pick | Hardware | Licences | Outcome |
|---|---|---|---|---|
| **A — SAM 3D as async fallback** | If a 24 GB box is available | 8 GB primary + 24 GB secondary | Apache-2.0 + SAM License | Highest quality, generative fallback for non-catalog items |
| **B — Pure Apache-2.0 retrieval** | Single-box deployment, simplest legal posture | 8 GB only | 100 % Apache-2.0/MIT | No generative fallback; long tail gets nearest library match flagged "low confidence" |
| **C — Stable Fast 3D PBR fallback** | If SCS revenue < US$1M | 8 GB only | Apache-2.0 + Stability Community | Best material fidelity, revenue-cap risk |

---

## 4. Files written in this session

| File | Purpose |
|---|---|
| [.env](.env) | Server + Python config with absolute `PYTHON_PATH` |
| [MODEL_SURVEY_SCS.md](MODEL_SURVEY_SCS.md) | 10-model survey spanning all pipeline stages (retrieval, segmentation, depth, generation) |
| [SESSION_REPORT.md](SESSION_REPORT.md) | This file |
| [OFFICE_FURNITURE_DETECTION_BENCHMARK.md](OFFICE_FURNITURE_DETECTION_BENCHMARK.md) | 10 detection-specific models for office furniture — comparative analysis |
| [scripts/test_furniture_detection.py](scripts/test_furniture_detection.py) | Runnable Python script that loads each of the 10 detection models and runs them on a sample image |

Persistent memory saved at `~/.claude/projects/.../memory/project_scs.md` documenting SCS as the project owner, the four hard requirements, and the hardware envelope — so future sessions inherit this context.

---

## 5. Outstanding work (in priority order)

1. **Test the 10 detection models on real SCS office photos.** Use [scripts/test_furniture_detection.py](scripts/test_furniture_detection.py) on 10–30 actual office photos. Record per-model precision/recall by category against ground truth. The model with highest recall for SCS's 11 categories becomes the front-of-pipeline detector.
2. **Replace `yolov8n-seg.pt` (AGPL) with SAM 2.1** in [backend/python-scripts/inference_base.py](backend/python-scripts/inference_base.py). Delete the AGPL binary from the repo root.
3. **Pull the CLIP fine-tuned checkpoint** (`models/clip_office/best_model.pt`, 354 MB) from the `Dimitres.Iteration3` branch into this branch (currently missing).
4. **Decide between deployment Paths A, B, C** above before wiring fallback.
5. **Build the Amazon Berkeley Objects subset** (Sprint 4.5 of PIVOT_BLUEPRINT.md) — curate ~50 clean office furniture meshes, normalise, store metadata.
6. **Pre-compute DINOv2 embeddings for the ABO subset** (Sprint 5) and wire the retrieval call into `inference_base.py:classify_object_clip`.
7. **Run the SAM 3D Objects smoke test** on the 24 GB secondary box per the work estimate (1.5–2.5 hours).
