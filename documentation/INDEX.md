# Documentation Index — 3DpicToIFCModeling
**Branch:** `all-documentation`  
**Team:** Dimi (Engineering Lead) · Gulriz (Research & Organisation Lead)  
**Last updated:** 2026-05-05

This folder collects every documentation file written across all six branches of the project, in the order they were produced. Below the document list you will find a detailed breakdown of how the code components differ between each branch — what each branch actually does differently at the function level.

---

## Documents in This Folder

| # | File | Source branch | What it covers |
|---|------|--------------|----------------|
| 01 | [README.md](01_README.md) | `main` | Project overview, stack, install, pipeline flowchart |
| 02 | [FULL_DOCUMENTATION.md](02_FULL_DOCUMENTATION.md) | `main` | Full pipeline technical reference |
| 03 | [DEVELOPMENT_ROADMAP_PHASE2.md](03_DEVELOPMENT_ROADMAP_PHASE2.md) | `main` | 8-sprint Phase 2 plan (generic Member 1 / Member 2 labels) |
| 04 | [TEAM_ROADMAP.md](04_TEAM_ROADMAP.md) | `main` | Same roadmap, named Dimi + Gulriz |
| 05 | [TRIPOSR_CHANGES_AND_LESSONS.md](05_TRIPOSR_CHANGES_AND_LESSONS.md) | `main` | 9 TripoSR iterations, outcomes, and hard lessons |
| 06 | [INSTALLATION_COMPLETE.md](06_INSTALLATION_COMPLETE.md) | `main` | Verified working environment snapshot |
| 07 | [WORK_CHECKPOINT.md](07_WORK_CHECKPOINT.md) | `main` | Mid-dev checkpoint: state, blockers, decisions |
| 08 | [API_REFERENCE.md](08_API_REFERENCE.md) | `main` | All API endpoints, schemas, error codes, curl examples |
| 09 | [SETUP_GUIDE.md](09_SETUP_GUIDE.md) | `main` | Step-by-step setup for a new developer |
| 10 | [OPTIMIZATION_GUIDE.md](10_OPTIMIZATION_GUIDE.md) | `main` | GPU tuning, mesh targets, xeokit rendering tips |
| 11 | [README_PHASE1_EARLY.md](11_README_PHASE1_EARLY.md) | `File-4-21-2026` | First commit — one-line stub, project day zero |
| 12 | [PHASE2_SPRINTS.md](12_PHASE2_SPRINTS.md) | `phase-2-sprints` | Deep technical breakdown of all 8 sprints |

**Recommended reading order for a new developer:**  
`01` → `09` → `02` → `05` → `04` → `12` → `08`

---

## Branch-by-Branch Code Comparison

This section explains what each branch does differently in terms of actual code components — not just documentation.

---

### `File-4-21-2026` — Project Day Zero
**Created:** 21 April 2026  
**State:** Empty scaffold, no working code.

- `README.md` contains one line: `# 3DpicToIFCModeling`
- No Python scripts, no Node server, no frontend
- Exists only as the initial GitHub push that created the repository

---

### `phase-1-infrastructure` — Working Skeleton
**Purpose:** Get the full stack running end-to-end, even if 3D quality is placeholder-level.

**What it does differently from day zero:**
- Full Node.js/Express backend (`backend/server.js`) with routes for generate, export, objects, pipeline, debug
- xeokit SDK integrated into the frontend viewer (`frontend/js/xeokitViewer.js`)
- GLB loading via `XKTLoaderPlugin` or `OBJLoaderPlugin`
- `inference_base.py` — shared utilities (log, error_exit, success_exit, depth mesh generators)
- `run_triposr.py` — calls the real TripoSR weights (stabilityai/TripoSR) via `TSR.from_pretrained`
- `saveIFC.py` — **template string version** (broken: outputs IFC2x3 with hardcoded placeholder entries, no actual mesh geometry)
- `ifcExporter.js` — passes objects as separate shell args (fragile)
- No objectId→glbPath mapping in frontend — export cannot find the GLB files

**Key limitation:** IFC export produces syntactically valid but geometrically empty files. Opening in Revit shows an empty building.

---

### `Original-TripoSR` — Baseline Snapshot + Sprint Scaffold
**Purpose:** Preserve the unmodified TripoSR pipeline as a reference baseline, then receive the Phase 2 sprint code on top.

**`run_triposr.py` — what it does:**
- Background removal: **rembg (U²-Net)** only — no SAM2
- Orientation: **centroid heuristic** — `if mesh.vertices[:, 1].mean() > 0.05: flip` (unreliable on objects with heavy bases like chair wheels)
- Smoothing: **Laplacian** (`trimesh.smoothing.filter_laplacian`, 5 iterations) — shrinks the mesh slightly
- Colour: **mean pixel average** over the rembg foreground mask — picks up warm background pixels, often produces yellow/beige tints
- Component filtering: keeps only components with >0.5% face ratio, rejects spike artifacts by compactness ratio

**`saveIFC.py` — what it does:**
- **Real ifcopenshell IFC4** with `IfcTriangulatedFaceSet` geometry (ported from main)
- Loads each GLB with trimesh, decimates to ≤8000 faces, writes actual vertex/face arrays
- Applies position, rotation, scale transforms before writing

**Additional Python scripts (Phase 2 sprints, not in `main`):**
- `run_instantmesh.py` — Zero123++ multi-view + LRM reconstruction (with YOLO+DPT fallback)
- `run_trellis.py` — Microsoft TRELLIS SLAT diffusion (MIT), TripoSR fallback
- `run_hunyuan3d.py` — Hunyuan3D-2 DiT shape gen + texture bake, fallback chain
- `classify_object.py` — YOLO detection + 24-class office object taxonomy → IFC type mapping
- `finetune_yolo_office.py` — YOLO fine-tuning scaffold for office datasets
- `spatial_layout.py` — OR-Tools CP-SAT no-overlap layout solver with ergonomic clearances
- `atiss_layout.py` — ATISS autoregressive scene synthesis wrapper + fine-tune entry
- `convert_to_xkt.py` — IFC → GLTF → XKT binary conversion (gltf2xkt CLI or JSON fallback)
- `test_pipeline.py` — end-to-end test runner for all models + IFC + classify + layout

**Frontend:** Original model selection UI (InstantMesh, StableFast3D, TripoSR only — no TRELLIS/Hunyuan3D buttons)

---

### `TripoSR-SAM2-Humphrey-Enhanced` — TripoSR Quality Push
**Purpose:** Push TripoSR output quality as far as possible within the single-view architecture constraint.

**`run_triposr.py` — what it does differently from `Original-TripoSR`:**

| Component | Original-TripoSR | TripoSR-SAM2-Humphrey-Enhanced |
|-----------|-----------------|-------------------------------|
| Background removal | rembg only | **SAM2** (sam2.1-hiera-tiny) with 5 click prompts at centre/offset positions; rembg fallback if SAM2 fails |
| Orientation fix | Centroid Y heuristic | **Face-normal area vote** — sums face areas where normals point up vs down; `if down_area > up_area: flip`. More robust on asymmetric objects |
| Smoothing | Laplacian (5 iters) | **Humphrey smoothing** (`filter_humphrey`, β=0.5) — volume-preserving, doesn't shrink the mesh |
| Colour | Mean pixel average | **K-means dominant colour** (k=3, scipy) — picks the most representative colour cluster from the foreground mask, ignores background bleed-through |

**`saveIFC.py`:** Still the **old broken template string version** — IFC2x3 with no geometry. This branch's export is non-functional.

**`ifcExporter.js`:** Old multi-arg version — fragile shell argument passing.

**No sprint scripts** — this branch contains only the TripoSR quality changes, not the Phase 2 sprint code.

**Key lesson from this branch:** Even with all four improvements applied, TripoSR still cannot reconstruct occluded surfaces (chair legs, object backs). The architecture is fundamentally single-view. This finding drove the decision to add InstantMesh, TRELLIS, and Hunyuan3D-2 in Phase 2.

---

### `main` — Production Branch
**Purpose:** The tested, stable version of the full pipeline. Code here has been validated end-to-end.

**`run_triposr.py`:** Same as `TripoSR-SAM2-Humphrey-Enhanced` — SAM2 + Humphrey + K-means + face-normal vote. This is the best TripoSR implementation.

**`saveIFC.py`:** **Real ifcopenshell IFC4** — complete rewrite. Produces files with actual `IfcTriangulatedFaceSet` geometry that opens correctly in Revit, BIM Vision, and BlenderBIM.

**`ifcExporter.js`:** Fixed — single `JSON.stringify(array)` arg instead of multiple shell args.

**`frontend/js/index.js`:** Fixed — `window._objectGlbMap` tracks `objectId → serverGlbPath`. After export, triggers a browser `<a>` download of the IFC file automatically.

**`frontend/js/exporter.js`:** Fixed — `prepareSceneForExport()` looks up `glbMap[obj.id]` and filters out objects without a GLB path before sending to the export route.

**No sprint scripts** — `main` has the production TripoSR + export pipeline but does not include the Phase 2 new model scripts (`run_trellis.py`, `run_hunyuan3d.py`, `spatial_layout.py`, etc.).

**Frontend:** Original three-model UI (InstantMesh, StableFast3D, TripoSR).

---

### `phase-2-sprints` — Full Phase 2 Implementation
**Purpose:** All 8 Phase 2 sprints implemented and working, on top of the Original-TripoSR baseline (not the SAM2-enhanced version).

**`run_triposr.py`:** **Baseline version** (rembg + Laplacian + centroid + mean colour) — same as `Original-TripoSR`. The sprint branch intentionally keeps the simpler baseline so the new models (InstantMesh, TRELLIS, Hunyuan3D-2) are the focus.

**`saveIFC.py`:** **Real ifcopenshell IFC4** — same as `main` (ported as a pre-sprint fix).

**`ifcExporter.js`:** Fixed single-arg version (same as `main`).

**Frontend:** Extended model UI — adds **TRELLIS** and **Hunyuan3D-2** buttons to the model selection sidebar.

**`backend/services/pipeline.js`:** Registers all 5 models: `instantmesh`, `stablefast3d`, `triposr`, `trellis`, `hunyuan3d`.

**New Python scripts exclusive to this branch:**

| Script | What it does |
|--------|-------------|
| `run_instantmesh.py` | Zero123++ (6 orbital views) → LRM reconstruction → PBR colour. Falls back to YOLO+DPT if weights absent |
| `run_trellis.py` | TRELLIS SLAT diffusion → mesh decoder → GLB. Falls back to TripoSR |
| `run_hunyuan3d.py` | Hunyuan3D-2 DiT shape generation → UV texture bake. Falls back to TRELLIS → TripoSR chain |
| `classify_object.py` | YOLO detection → 24-class office taxonomy → IFC type + material + BIM properties |
| `finetune_yolo_office.py` | Writes dataset YAML, runs `yolo train`, copies best weights to `models/yolo/office_seg.pt` |
| `spatial_layout.py` | CP-SAT integer program: places furniture in room with no overlap + wall margin + ergonomic clearances. OR-Tools. |
| `atiss_layout.py` | ATISS autoregressive layout generation. Falls back to OR-Tools CP-SAT. Includes `--finetune` for training on office data |
| `convert_to_xkt.py` | IFC → GLTF (ifcopenshell geom) → XKT binary (gltf2xkt CLI). Falls back to XKT JSON |
| `test_pipeline.py` | Runs all models + IFC export + classify + layout, reports PASS/FAIL table, exits 0/1 |

**New Node.js AI adapters:**
- `backend/ai/trellis.js` — routes `trellis` model calls to `run_trellis.py`
- `backend/ai/hunyuan3d.js` — routes `hunyuan3d` model calls to `run_hunyuan3d.py`

**New API endpoints:**
- `POST /api/export/xkt` — converts an existing IFC file to XKT binary format
- `POST /api/objects/layout` — runs the spatial layout solver for a given room and object list

---

## Component Difference Matrix

The table below shows at a glance how the key system components differ between branches:

| Component | `Original-TripoSR` | `TripoSR-SAM2-Humphrey-Enhanced` | `main` | `phase-2-sprints` |
|-----------|:-----------------:|:--------------------------------:|:------:|:-----------------:|
| **Background removal** | rembg | SAM2 + rembg fallback | SAM2 + rembg fallback | rembg |
| **Orientation fix** | Centroid Y heuristic | Face-normal area vote | Face-normal area vote | Centroid Y heuristic |
| **Mesh smoothing** | Laplacian | Humphrey (volume-preserving) | Humphrey | Laplacian |
| **Colour extraction** | Mean pixel average | K-means dominant colour (k=3) | K-means dominant colour | Mean pixel average |
| **IFC export geometry** | Real IFC4 mesh | Broken template strings | Real IFC4 mesh | Real IFC4 mesh |
| **Frontend download trigger** | No | No | Yes | Yes |
| **objectId → glbPath map** | No | No | Yes | Yes |
| **InstantMesh (real LRM)** | Yes (scaffold) | No | No | Yes (scaffold) |
| **TRELLIS** | Yes (scaffold) | No | No | Yes (scaffold) |
| **Hunyuan3D-2** | Yes (scaffold) | No | No | Yes (scaffold) |
| **YOLO office classifier** | Yes | No | No | Yes |
| **OR-Tools spatial layout** | Yes | No | No | Yes |
| **ATISS layout synthesis** | Yes | No | No | Yes |
| **XKT export** | Yes | No | No | Yes |
| **End-to-end test runner** | Yes | No | No | Yes |

---

## What to Use Each Branch For

- **`main`** — use this if you want the best TripoSR output quality (SAM2 + Humphrey + K-means) with a working IFC export. No new model scripts.
- **`TripoSR-SAM2-Humphrey-Enhanced`** — use this only for comparison with `main`; the IFC export is broken on this branch.
- **`Original-TripoSR`** — baseline TripoSR reference + all Phase 2 sprint scripts. Use this as the starting point for Phase 2 development.
- **`phase-2-sprints`** — same sprint code as `Original-TripoSR` plus the `PHASE2_SPRINTS.md` deep-dive document. The canonical Phase 2 branch.
- **`all-documentation`** (this branch) — documentation only. Based on `main` code, with the `documentation/` folder added. No sprint scripts.
