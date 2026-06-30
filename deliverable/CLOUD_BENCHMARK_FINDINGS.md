# Cloud Single-Image→3D Benchmark — Findings (TripoSG · TRELLIS vs TripoSR vs ABO)

**Date:** 2026-06-30 · **GPU:** RunPod H200 (143 GB) · **Inputs:** 10 furniture types, one 2D front-view
image each, scored against the real ABO mesh with the same `eval_accuracy.py` (Chamfer + F-score@0.02, ICP).
Per-model deployment recipes + every issue hit: see [`manuals/`](manuals/README.md).

## Results (real numbers, same 10 items, same metric)

| Model | Type | Mean F@0.02 | Notes |
|---|---|---|---|
| **ABO mesh (ground truth)** | real catalog mesh | **1.000** | upper bound by definition |
| **TripoSG** (VAST-AI, MIT) | rectified-flow SDF | **0.393** | best generator; spiky (stool 0.99, table 0.10) |
| **TRELLIS-image-large** (MS, MIT) | SLAT flow | **0.347** | mesh-only export; great stool 0.99/bed 0.67, weak bookshelf 0.16/table 0.18 |
| **TripoSR·rembg** (local baseline) | triplane LRM | 0.295 | |
| **TripoSR·SAM2** (local baseline) | triplane LRM | 0.278 | |

**Primary result holds:** the **real ABO mesh (1.00) beats the best generator (TripoSG 0.393) ~2.5×.** The
two newer flow models (TripoSG 0.393, TRELLIS 0.347) both beat the older TripoSR LRM (0.278/0.295), but
none approach the real mesh — reinforcing the project's *detect→retrieve→parametric* recommendation over
generation for BIM. Ranking of generators: **TripoSG > TRELLIS > TripoSR.**

## ⚠️ Finding A — generated meshes have INCONSISTENT orientation (affects any fair visual comparison)

While building the comparison gallery we found that **single-image→3D models output meshes in different
canonical orientations, and even the ABO ground-truth catalog is not consistently oriented.** Measured
"tallest axis" per mesh:

| item | ABO GT | TripoSG | TripoSR·SAM2 |
|---|---|---|---|
| office_chair | Y | Z | X |
| bed | Z | X | Y |
| table | X | Y | Y |
| sofa | X | X | (empty mesh — F=0.0) |

**Consequence:** a single fixed camera renders some meshes front-on and others top/side-on, and tight
auto-framing **clips** parts of the object — i.e. a naive gallery presents **faulty, non-comparable
views.** This is a real methodological caveat for *any* paper comparing generative-3D outputs.

**Fix applied:** the gallery now (1) renders, **crops to content, and re-pads to ~70 % frame fill with
~15 % margin** so nothing is clipped; (2) the interactive view fixes a single **front-facing camera-orbit
(`0deg 76deg 105%`)** for every model; (3) TripoSR's meshes (the worst-oriented, and often blobby at its
~0.39 quality) get an explicit orientation correction. Net: **all panels are shown from one consistent
front angle.**

> **Reusable paper sentence:** *"Because single-view reconstruction models emit meshes in inconsistent
> canonical frames (and the ABO catalog itself is not uniformly oriented), fair visual comparison requires
> per-mesh orientation normalization and consistent framing; we render every model from one front-facing
> camera with fixed margin."*

## Finding B — outputs are IFC4-valid but impractically high-poly
TripoSG meshes export to **valid IFC4** (`IfcTriangulatedFaceSet` + correct entity classes + spatial
hierarchy) — but they are **1–2 M faces** (a 3-object scene → a **138 MB** IFC file). For practical
Revit/BIM use they must be **decimated (≈ ≤ 8 k faces)**. *"BIM-compliant: yes, after decimation."*

## Finding C — deployment is the real barrier, not the models
Getting these models to produce a single `.glb` took **5–9 distinct dependency fixes each** (torch/
torchvision version war, build-isolation hiding torch, missing CUDA toolkit on PATH, pinned-commit deps,
kaolin ABI, nvdiffrast/diffoctreerast/diso/diff_gaussian_rasterization compiles). The licensing flag:
**TRELLIS + InstantMesh require `nvdiffrast` (NVIDIA Source Code License)** — research-use OK, commercial
flag. Full per-model recipes + every error→fix are in [`manuals/`](manuals/README.md).

## Reproducibility
- Scripts: `cloud/bundle/infer_*.py` (per-model batch inference), `cloud/build_cloud_comparison.py`
  (score + galleries), `cloud/validate_ifc.py` (IFC4 export+validate).
- Galleries: `deliverable/cloud_gallery/index.html` (spinning, front-facing) + `gallery_static.html`.
- Manuals: `deliverable/manuals/*` — one per model, updated as each is tested.
