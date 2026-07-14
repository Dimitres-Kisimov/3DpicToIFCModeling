# Project History — Everything Done So Far

**Date compiled:** 2026-05-21
**Current branch:** `retrieval-pivot-blueprint`
**Purpose:** A single document that reconstructs every meaningful chunk of work across all branches of this repo, so anyone (including future-us) can see what was tried, what shipped, and what was lost or stranded on a side branch.

---

## TL;DR — what you have right now

You have **three distinct lines of work** sitting on different branches:

| Line | Branch | What it is | Status |
|---|---|---|---|
| A. Infrastructure + TripoSR baseline | `main`, `phase-1-infrastructure` | Working end-to-end Node/Express + Python + xeokit pipeline, single-view TripoSR mesh, **broken IFC export** (template strings, no geometry) | ✅ Shipped (with broken IFC) |
| B. Real IFC4 export fix | `main` (commit `3c007eb`) | Rewrote `saveIFC.py` to produce real `IfcTriangulatedFaceSet` geometry that opens in Revit/Blender. Frontend download trigger. | ✅ Shipped to `main`, **NOT on `Dimitres.Iteration3`** |
| C. 8-sprint Phase 2 implementation | `Original-TripoSR` (commit `93c2a94`) | Real InstantMesh, TRELLIS, Hunyuan3D, XKT export, YOLO-based object classification, OR-Tools spatial layout, ATISS, test runner | ✅ Built, **NOT on `Dimitres.Iteration3`** |
| D. CLIP fine-tuning pivot | `Dimitres.Iteration3` (commits `a458b80`, `52c1062`) | Downloaded 13,752 Open Images, fine-tuned CLIP on 11 office furniture categories. Trained checkpoint at `models/clip_office/best_model.pt`. | ✅ Done |
| E. Retrieval-pivot blueprint | `retrieval-pivot-blueprint` (this branch, commit `10d1d9f`) | Architectural decision: generative image-to-3D is wrong tool for catalog use case; pivot to retrieval. | ✅ Documented in [PIVOT_BLUEPRINT.md](PIVOT_BLUEPRINT.md) |

**Critical fact:** Lines B and C exist but were never merged into `Dimitres.Iteration3`. The current iteration branch diverged before they landed. We need to consciously decide what to bring forward.

---

## Branch map (chronological)

```
Initial commit (327586a)
    │
    ├── a801ea0 — Initial PySide6 desktop app (multi-AI image→IFC)
    │
    ▼
File-4-21-2026 (project day zero, empty README scaffold)
    │
    ▼
phase-1-infrastructure
    ├── Phase 1: backend scaffold, Express server, Python bridge
    ├── Phase 3-5: AI adapter scaffolds, mesh processing, object manipulation
    ├── Phase 6-7: IFC export skeleton (BROKEN — template strings only)
    ├── Phase 8: testing, optimization, documentation
    ├── xeokit viewer init fix + local serving
    │
    ▼
main  (= phase-1-infrastructure + real-AI-depth-mesh + GPU tuning + TripoSR quality fixes)
    │
    ├── README rewrite, Phase 2 roadmap, TEAM_ROADMAP
    │
    ├── 3c007eb — fix: real IFC4 export ←──── LINE B
    │
    ▼
Original-TripoSR
    └── 93c2a94 — feat: all 8 sprints + export fixes ←──── LINE C
        ├── Sprint 1: Real InstantMesh (Zero123++ + LRM)
        ├── Sprint 2: TRELLIS integration
        ├── Sprint 3: XKT export
        ├── Sprint 4: classify_object.py — 24-class YOLO + IFC taxonomy
        ├── Sprint 5: spatial_layout.py — OR-Tools CP-SAT
        ├── Sprint 6: atiss_layout.py — ATISS scene synthesis
        ├── Sprint 7: run_hunyuan3d.py — Hunyuan3D-2 + texture bake
        └── Sprint 8: test_pipeline.py, frontend model picker, pipeline.js
    │
phase-2-sprints (= Original-TripoSR + PHASE2_SPRINTS.md docs)
    │
TripoSR-SAM2-Humphrey-Enhanced (= reverted SAM2+Poisson+Humphrey experiment)
    │
all-documentation (consolidated documentation/ folder with all 13 docs)
    │
enhanced-pipeline-improvements (= Dimitres.Iteration3 alias, recent CLIP work)
    │
Dimitres.Iteration3 ←─── CURRENT WORK (diverged from main BEFORE 3c007eb)
    ├── 4677eb5 — Depth Anything V2 + CLIP classification + metric IFC dimensions
    ├── 18c9ce8 — SAM2 segmentation + Humphrey smoothing + k-means color
    ├── a458b80 — CLIP fine-tuning pipeline (download + train + evaluate)
    └── 52c1062 — fix: Open Images downloader S3 direct URLs
    │
    ▼
retrieval-pivot-blueprint ←─── YOU ARE HERE
    └── 10d1d9f — docs: PIVOT_BLUEPRINT.md
```

---

## Line A — Phase 1 infrastructure (shipped)

**Where:** `phase-1-infrastructure`, ancestor of `main`.

**What works:**
- Node.js / Express server on port 3000
- Python subprocess bridge for AI scripts
- xeokit SDK integrated into frontend (`xeokitViewer.js`, GLB loader)
- REST API: `/api/generate`, `/api/objects`, `/api/export/ifc`, `/api/debug/*`
- TripoSR (`stabilityai/TripoSR`) end-to-end: photo → mesh → display
- GPU acceleration via CUDA (PyTorch 2.11 with CUDA)
- Inventory + transform controls in browser
- Logging, error handling, environment config (`.env`)

**Documented in:**
- [documentation/01_README.md](all-documentation:documentation/01_README.md)
- [documentation/06_INSTALLATION_COMPLETE.md](all-documentation:documentation/06_INSTALLATION_COMPLETE.md)
- [documentation/09_SETUP_GUIDE.md](all-documentation:documentation/09_SETUP_GUIDE.md)
- [WORK_CHECKPOINT.md](WORK_CHECKPOINT.md)

**Known weakness:** IFC export wrote a hardcoded IFC2x3 template with placeholder `IfcFurnishingElement` entries and **no actual mesh geometry**. Opening in Revit produced empty files.

---

## Line B — Real IFC4 export fix (shipped to `main`, missing from `Dimitres.Iteration3`)

**Where:** `main`, commit `3c007eb` (2026-05-05).

**What it does:**
- Complete rewrite of [backend/python-scripts/saveIFC.py](backend/python-scripts/saveIFC.py):
  - Uses `ifcopenshell` to write real IFC4
  - Loads each GLB with `trimesh`, decimates to ≤8000 faces
  - Creates `IfcTriangulatedFaceSet` with real vertex/face arrays
  - Proper IFC hierarchy: Project → Site → Building → Storey → Furniture
  - Applies per-object position and scale
  - Accepts objects as a single JSON-string arg (no shell-arg-limit issues)
- [backend/services/ifcExporter.js](backend/services/ifcExporter.js): single JSON arg instead of multiple shell args
- [frontend/js/index.js](frontend/js/index.js): `window._objectGlbMap` registry + browser file-download trigger after export
- [frontend/js/exporter.js](frontend/js/exporter.js): enriches scene objects with `glbPath` before export

**Impact:** IFC files now contain real geometry and open in Revit, BIM Vision, Blender IFC import, etc.

**Status on `Dimitres.Iteration3`:** ❌ NOT present. This branch diverged from `main` before this commit landed. Anyone exporting IFC from the current iteration branch will get the broken template version.

---

## Line C — 8-sprint Phase 2 implementation (built on Original-TripoSR, missing from Dimitres.Iteration3)

**Where:** `Original-TripoSR`, commit `93c2a94` (2026-05-05).

This is a large coherent block of work. Full technical detail in [documentation/12_PHASE2_SPRINTS.md](all-documentation:documentation/12_PHASE2_SPRINTS.md). Summary:

| Sprint | File(s) | What it adds | License |
|---|---|---|---|
| 1 | `run_instantmesh.py` | Real two-stage pipeline: Zero123++ (6-view synthesis) + LRM reconstruction. Falls back to YOLO+DPT depth mesh. | Apache 2.0 |
| 2 | `run_trellis.py`, `backend/ai/trellis.js` | Microsoft TRELLIS image-large (SLAT diffusion). Falls back to TripoSR. | MIT |
| 3 | `convert_to_xkt.py`, `exportRoutes.js` | IFC → GLTF → XKT via `gltf2xkt` CLI, JSON fallback. `POST /api/export/xkt`. | — |
| 4 | `classify_object.py`, `finetune_yolo_office.py` | YOLO instance segmentation → 24-class IFC taxonomy (IfcChair, IfcSofa, IfcTable, IfcElectricAppliance, …) + fine-tuning scaffold | ⚠️ AGPL (YOLO) |
| 5 | `spatial_layout.py`, `objectRoutes.js` | OR-Tools CP-SAT no-overlap 2D placement with ergonomic clearance presets per category. `POST /api/objects/layout`. | Apache 2.0 |
| 6 | `atiss_layout.py` | ATISS autoregressive transformer for scene synthesis + OR-Tools fallback + 3D-FRONT fine-tune entry. | MIT |
| 7 | `run_hunyuan3d.py`, `hunyuan3d.js` | Multi-view diffusion + texture baking via `Hunyuan3DPaintPipeline`. Falls back to TRELLIS → TripoSR. | ⚠️ Tencent Community License |
| 8 | `test_pipeline.py`, `pipeline.js`, `frontend/index.html` | End-to-end test runner across all 5 models + IFC + classify + layout. Frontend model picker shows all 5 options. | — |

**Status on `Dimitres.Iteration3`:** ❌ NONE of this work is on the current iteration branch. It exists only on `Original-TripoSR` (and `phase-2-sprints` which has the docs).

**What of this is still valuable under the new retrieval pivot?**

| Worth salvaging | Reason |
|---|---|
| `saveIFC.py` rewrite (real IFC4) | Foundation for any export. Already on `main`. |
| `spatial_layout.py` (OR-Tools CP-SAT) | Sprint 5 of new plan still uses this. Clearances and no-overlap logic is reusable. |
| `convert_to_xkt.py` (XKT export) | Sprint 3 of new plan still needs this. |
| `test_pipeline.py` (test runner) | Adaptable to retrieval pipeline. |
| `classify_object.py` IFC taxonomy table | The 24-class map (label → IfcChair etc.) is reusable for our retrieval results. ⚠️ Replace the YOLO inference step with our CLIP classifier. |
| `frontend/index.html` model picker | Already has UI structure for multiple model options. |

| Deprioritized | Reason |
|---|---|
| `run_instantmesh.py` (Zero123++ + LRM) | Generative; fallback only under new plan |
| `run_trellis.py` | Generative; fallback only under new plan |
| `run_hunyuan3d.py` | Generative + Tencent Community License risk |
| `atiss_layout.py` | Still relevant for sprint 6 (after retrieval), but lower priority than getting retrieval working |
| `finetune_yolo_office.py` | AGPL risk + duplicates the CLIP work we already did |

---

## Line D — CLIP fine-tuning pivot (current iteration branch)

**Where:** `Dimitres.Iteration3`, commits `4677eb5` → `52c1062`.

**What it adds:**
- [scripts/download_openimages.py](scripts/download_openimages.py) — direct S3 download of Google Open Images V7. No API key, no `awscli`. CC BY 4.0 data.
- [scripts/train_clip_office.py](scripts/train_clip_office.py) — fine-tunes CLIP-ViT-B/32 on 11 office furniture categories (linear probe or LoRA).
- [scripts/evaluate_clip.py](scripts/evaluate_clip.py) — side-by-side zero-shot vs fine-tuned CLIP comparison.
- **Trained checkpoint:** [models/clip_office/best_model.pt](models/clip_office/best_model.pt) (354 MB, dated May 7).
- **Dataset on disk:** 13,752 office furniture images across 11 categories — see [data/office_images/manifest.csv](data/office_images/manifest.csv).
- [backend/python-scripts/inference_base.py](backend/python-scripts/inference_base.py): now auto-loads the fine-tuned model when present; falls back to zero-shot CLIP otherwise.

**Image counts per category:**
- office_chair: 1874 · cabinet: 1879 · bookshelf: 1830 · keyboard: 1778 · monitor: 1765 · lamp: 1601 · desk: 712 · desk_lamp: 712 · mouse: 640 · table: 634 · filing_cabinet: 326 ⚠️ (imbalanced)

**Also on this branch (from earlier commits inherited from main):**
- Depth Anything V2 for metric scale estimation (`estimate_metric_scale()` in `inference_base.py`)
- SAM2 segmentation (`generate_segmented_depth_mesh()` in `inference_base.py`)
- YOLO + Humphrey smoothing experimentation (reverted commit `345baf6`, then partially restored)

**Status of evaluation:** The checkpoint exists but there's no on-disk evaluation report. Running `scripts/evaluate_clip.py` would tell us per-class accuracy on the test split.

---

## Line E — Retrieval pivot blueprint (this branch)

**Where:** `retrieval-pivot-blueprint`, commit `10d1d9f` (2026-05-21).

**What it is:** [PIVOT_BLUEPRINT.md](PIVOT_BLUEPRINT.md) — architectural decision to stop chasing generative image-to-3D for a catalog use case and switch to retrieval against a clean CAD library.

**Key points:**
- Generative models can't produce 1:1 furniture reconstructions because the problem is mathematically ill-posed (single photo has no info about hidden sides).
- Pivot architecture: photo → CLIP classifier (we have it) → DINOv2 embedding → nearest-neighbour search in clean CAD library → Depth Anything V2 scaling (we have it) → IFC.
- Primary library: Amazon Berkeley Objects (CC BY 4.0, 7,953 artist-made meshes with PBR materials).
- License audit: YOLOv8 (AGPL) flagged for replacement; Hunyuan3D Community License flagged for skip; SAM 3 / SAM 3D not available.
- Open question: how to handle long-tail items not in the library.

---

## Documentation snapshot (what already exists where)

On `all-documentation` branch, [`documentation/`](documentation/) contains 13 docs collected from across branches. The index ranks recommended reading order for a new developer as: `01 → 09 → 02 → 05 → 04 → 12 → 08`.

Important documents that already exist (don't recreate):

| Doc | Branch | What it covers |
|---|---|---|
| `documentation/01_README.md` | `all-documentation` | Project overview |
| `documentation/02_FULL_DOCUMENTATION.md` | `all-documentation` | Full technical reference |
| `documentation/03_DEVELOPMENT_ROADMAP_PHASE2.md` | `all-documentation` | Original 8-sprint plan |
| `documentation/05_TRIPOSR_CHANGES_AND_LESSONS.md` | `all-documentation` | 9 TripoSR iterations + hard lessons |
| `documentation/08_API_REFERENCE.md` | `all-documentation` | All API endpoints + schemas |
| `documentation/12_PHASE2_SPRINTS.md` | `all-documentation` | Deep technical breakdown of all 8 sprints |
| `DEVELOPMENT_ROADMAP_PHASE2.md` | `Dimitres.Iteration3` | Same Phase 2 plan |
| `TripoSR_CHANGES_AND_LESSONS.md` | `Dimitres.Iteration3` | TripoSR iteration log |
| `WORK_CHECKPOINT.md` | `Dimitres.Iteration3` | Phase 1 checkpoint |
| `PIVOT_BLUEPRINT.md` | `retrieval-pivot-blueprint` | The new retrieval architecture |
| `PROJECT_HISTORY.md` | `retrieval-pivot-blueprint` | This document |

---

## What this means for next moves

1. **Decide what to merge forward into the retrieval line.** Specifically: the real IFC4 export from `main` (commit `3c007eb`) is essential, and several utilities from `Original-TripoSR` (spatial_layout, convert_to_xkt, test_pipeline, IFC taxonomy from classify_object) are reusable. The generative model adapters should be left as fallback-only.

2. **Don't reinvent.** The 8-sprint work happened. Even if we're pivoting away from generative as the primary approach, the supporting infrastructure (export, layout, test runner) is real and should be carried over rather than rebuilt.

3. **The CLIP classifier is now the first stage of the retrieval pipeline.** It was originally Sprint 4 of the old roadmap; under the new blueprint it becomes the gate that picks which library bucket to search.

4. **License cleanup is overdue.** YOLOv8 (AGPL) is in the repo via `yolov8n-seg.pt` and the segmented depth mesh path in `inference_base.py`. For a commercial product, this needs to go — SAM 2 (Apache 2.0) already covers the segmentation role.

5. **The two big known-good baselines to remember:**
   - **Starting Point A** = `phase-2-sprints` @ `2d068d8` (user-named, in memory)
   - **Real IFC4 export** = `main` @ `3c007eb` (last point where export actually worked end-to-end)

These are the points to revert to if the current line breaks.
