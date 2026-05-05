# Phase 2 — Sprint Breakdown & Technical Specification

**Branch:** `phase-2-sprints`  
**Team:** Dimi (Engineering Lead) · Gulriz (Research & Organisation Lead)  
**Goal:** Evolve the baseline TripoSR single-image pipeline into a production-grade, multi-model office furniture reconstruction and spatial layout system that exports valid IFC4 files for use in BIM workflows.

---

## Background & Motivation

Phase 1 established the end-to-end skeleton: upload an image, run TripoSR, display the GLB in xeokit, and export an IFC file. However Phase 1 had three fundamental weaknesses that Phase 2 fixes:

1. **Export was fake.** The IFC files contained hardcoded template strings with no actual mesh geometry — opening them in Revit or Blender produced empty files.
2. **Only one model.** TripoSR is a single-view transformer. It cannot reconstruct occluded surfaces (chair legs, table undersides) because it only sees one angle. Multi-view models are required for production quality.
3. **Objects were dropped randomly into the scene.** There was no spatial intelligence — no collision avoidance, no ergonomic rules, no understanding of how office furniture relates to room geometry.

Phase 2 resolves all three, sprint by sprint.

---

## Export Fixes (Pre-sprint, foundational)

Before any sprint work, the broken export pipeline was repaired. This is the foundation everything else depends on.

### What was wrong
`saveIFC.py` wrote a hardcoded IFC2x3 template with placeholder `IfcFurnishingElement` entries but no geometry data. The `ifcExporter.js` Node service passed each object as a separate command-line argument (fragile, breaks on special characters). The frontend had no way to associate a loaded `objectId` with its server-side GLB path, and there was no download trigger after export.

### What was fixed

| File | Fix |
|------|-----|
| `backend/python-scripts/saveIFC.py` | Complete rewrite using `ifcopenshell` IFC4. Loads each GLB with `trimesh`, decimates to ≤8000 faces, creates `IfcTriangulatedFaceSet` with real vertex/face data, applies position/rotation/scale, writes valid IFC4. |
| `backend/services/ifcExporter.js` | Changed from multiple JSON shell args (`sys.argv[2]`, `sys.argv[3]`…) to a single `JSON.stringify(array)` arg — `sys.argv[2]` is the whole objects list. |
| `frontend/js/index.js` | Added `window._objectGlbMap = {}`. Every generated model is registered: `window._objectGlbMap[objectId] = glbPath`. After export, triggers a browser `<a>` download of the IFC file. |
| `frontend/js/exporter.js` | `prepareSceneForExport()` now looks up `glbMap[obj.id]` for each scene object. Objects without a GLB path are filtered out. |

**What this achieves:** IFC files exported from the browser now contain real mesh geometry. They open correctly in Revit, BIM Vision, Blender IFC import, and any other IFC4-compliant viewer. The user gets an automatic file download without needing to manually navigate to `/outputs/`.

---

## Sprint 1 — Real InstantMesh Pipeline

**File:** `backend/python-scripts/run_instantmesh.py`  
**Model:** `TencentARC/InstantMesh` (Apache 2.0)  
**Weights size:** ~7 GB  
**Download:** `huggingface-cli download TencentARC/InstantMesh --local-dir models/instantmesh`

### What is being done

Phase 1's InstantMesh was a YOLO+DPT depth-map mesh — it had nothing to do with the actual InstantMesh model. Sprint 1 replaces it with the real two-stage pipeline:

**Stage 1 — Zero123++ multi-view synthesis**  
Zero123++ (`sudo-ai/zero123plus-v1.2`) takes a single RGB image and generates 6 orbital views at fixed elevation angles (30° above, with 60° azimuth spacing). These are returned as a 2×3 grid image that is sliced into 6 individual 320×320 PIL frames. This gives the reconstruction model views of the object from multiple angles, solving the fundamental occlusion problem TripoSR has.

**Stage 2 — InstantMesh LRM reconstruction**  
The 6 views are fed into the Large Reconstruction Model (LRM) backbone that InstantMesh uses. LRM is a transformer trained on Objaverse that regresses a triplane NeRF representation from multi-view images. The triplane is then decoded into a dense mesh via marching cubes. The result is a closed, watertight mesh with geometry on all sides of the object — including the back, bottom, and occluded areas.

**Stage 3 — PBR colour from source image**  
The dominant foreground colour is extracted from the rembg alpha mask and applied as a `PBRMaterial(baseColorFactor=...)` so xeokit renders it with the correct colour.

**Fallback:** If InstantMesh weights are not downloaded, the script detects the `FileNotFoundError` and falls back to the original YOLO+DPT segmented depth mesh. The pipeline never crashes — it degrades gracefully.

### What this achieves
- Symmetric, complete 3D objects instead of front-face-only shells
- Correct chair legs, table undersides, object backs
- No post-processing hacks needed to fix orientation — LRM outputs in a consistent frame
- Same API surface as Phase 1: `run_instantmesh.py <image> <output.glb>`

---

## Sprint 2 — TRELLIS Integration

**File:** `backend/python-scripts/run_trellis.py`  
**AI adapter:** `backend/ai/trellis.js`  
**Model:** `microsoft/TRELLIS-image-large` (MIT License)  
**Weights size:** ~3 GB  
**Download:** `huggingface-cli download microsoft/TRELLIS-image-large --local-dir models/trellis`

### What is being done

TRELLIS (Structured LATent diffusion for 3D) is Microsoft Research's state-of-the-art image-to-3D model. Unlike TripoSR (deterministic regression) or InstantMesh (multi-view + LRM), TRELLIS uses a diffusion process operating in a structured 3D latent space (SLAT).

The pipeline:
1. The input image is embedded by a CLIP-based image encoder.
2. A sparse 3D U-Net diffusion model generates a SLAT (Structured LATent) representation — a sparse volumetric field encoding geometry and appearance.
3. Two decoders run in parallel: a Gaussian splatting decoder (for fast preview) and a mesh decoder (for export). We use the mesh decoder.
4. The mesh is extracted and exported as GLB.

TRELLIS tends to produce higher geometric fidelity than TripoSR on complex objects (multi-legged chairs, objects with holes, asymmetric furniture) because the diffusion process can explore the latent space rather than being locked to a single deterministic regression.

**Fallback:** TripoSR if weights are absent.

### What this achieves
- A second high-quality reconstruction path with MIT license (fully commercial)
- Better handling of topologically complex objects (chairs with spoke legs, shelving units)
- Geometry + appearance are jointly modelled — texture hints are baked into the shape
- TRELLIS + InstantMesh together cover a wide range of object types with complementary strengths

---

## Sprint 3 — XKT Export Pipeline

**File:** `backend/python-scripts/convert_to_xkt.py`  
**Route:** `POST /api/export/xkt` (added to `backend/routes/exportRoutes.js`)

### What is being done

IFC files are large and slow to parse in the browser. xeokit's native binary format, XKT (xeokit Binary Scene), loads 10–100× faster. Sprint 3 adds a server-side IFC→XKT conversion pipeline.

**Option A (highest fidelity): IFC → GLTF → XKT**
- `ifcopenshell.geom` extracts all `IfcProduct` geometry with world coordinates, assembles a trimesh scene, exports to GLTF.
- `gltf2xkt` CLI (from `@xeokit/xeokit-convert` npm package) converts GLTF → binary XKT v10.

**Option B (fallback): XKT JSON**
- When the `gltf2xkt` CLI is not installed, the script writes an XKT JSON file directly from ifcopenshell geometry data. This is browser-loadable by xeokit's `XKTLoaderPlugin` with `src` pointing at the JSON endpoint.

The conversion is triggered via `POST /api/export/xkt` with `{ ifcPath }` in the body. The response includes `xktUrl` pointing at `/outputs/<file>.xkt`.

### What this achieves
- Sub-second scene loading in the browser for complex multi-furniture IFC models
- XKT is the recommended format for xeokit production deployments
- Prepares the pipeline for a public demo where loading time matters

---

## Sprint 4 — Office Object Detection & Classification

**Files:**
- `backend/python-scripts/classify_object.py` — inference
- `backend/python-scripts/finetune_yolo_office.py` — training scaffold

### What is being done

When a user uploads a photo of an office chair, the system currently treats it as a generic `IfcFurnishingElement`. Sprint 4 adds an intelligent classification layer that:

1. **Detects the object** using YOLOv8 instance segmentation. The largest detected mask is taken as the primary object.
2. **Maps the YOLO class to an IFC type and material category** using a taxonomy table covering 24 office furniture classes:
   - Seating: `chair`, `couch`, `sofa` → `IfcChair`, `IfcSofa`, material: `textile_soft`
   - Tables: `dining table`, `desk`, `conference_table` → `IfcTable`, material: `wood_polished`
   - Electronics: `laptop`, `tv`, `monitor` → `IfcElectricAppliance`, material: `metal_brushed`
   - Storage: `bookshelf`, `filing_cabinet`, `cabinet` → `IfcFurnishingElement`, material: `wood_matte`
   - Other: `plant`, `printer`, `whiteboard`, `projector`, `lamp`, `telephone`, `coffee_machine`, `water_dispenser`, `safe`, `trash_bin`, `coat_rack`, `drawer`, `partition`

3. **Returns BIM properties** (LoadBearing, IsExternal, Occupancy) that can be embedded in the IFC file's property sets.

**Fine-tuning scaffold** (`finetune_yolo_office.py`):  
When labeled office image data is collected, this script:
- Writes the YOLO dataset YAML config automatically
- Runs `yolo train` with configurable epochs, image size, batch size, and device
- Copies the best weights to `models/yolo/office_seg.pt`

`classify_object.py` automatically uses `models/yolo/office_seg.pt` if present, otherwise falls back to the pretrained `yolov8n-seg.pt` COCO weights.

### What this achieves
- Every generated object is tagged with a semantically correct IFC type (not just `IfcFurnishingElement`)
- Material categories feed into a future material lookup table for visual differentiation in xeokit
- BIM properties are ready for handoff to Revit or Archicad without manual tagging
- A clear path to improve accuracy: collect labeled office photos → run `finetune_yolo_office.py`

---

## Sprint 5 — Spatial Positioning Engine (OR-Tools CP-SAT)

**File:** `backend/python-scripts/spatial_layout.py`  
**Route:** `POST /api/objects/layout` (added to `backend/routes/objectRoutes.js`)  
**Dependency:** `pip install ortools`

### What is being done

When multiple objects are generated and need to be placed in a room, Sprint 5 solves an optimisation problem: position all furniture pieces in the room such that:
- No two pieces overlap (including their ergonomic clearance zones)
- No piece is within 20 cm of a wall
- Objects can be rotated 0° or 90° to better fit the available space

**Algorithm: OR-Tools CP-SAT integer programming**  
The room is discretised to a 10 cm grid. For each furniture piece:
- A Boolean variable `rot` controls 0° vs 90° rotation
- Integer variables `x`, `z` represent the grid position of the padded bounding box origin (including clearance)
- `IntervalVar` objects define the 2D footprint of each piece in X and Z

The `AddNoOverlap2D` constraint ensures no two furniture footprints intersect. CP-SAT solves the constraint satisfaction problem with a 30-second timeout.

**Clearance presets by category:**
- Chair: 0.5 m, Desk: 0.8 m, Conference table: 1.0 m, Sofa: 0.6 m, Bookshelf: 0.3 m, Printer: 0.4 m, Default: 0.4 m

**Fallback:** If CP-SAT cannot find a feasible solution within 30 seconds (room too small for all objects), a simple row-layout fallback stacks objects left-to-right.

### What this achieves
- Legally correct office layouts with no furniture collision
- Ergonomic clearances respected by default (e.g. 80 cm in front of desks for chair pull-out)
- Automated spatial arrangement means users can generate 10 objects and drop them into a room without manually positioning each one
- API endpoint enables frontend to request a layout solve and apply the returned positions

---

## Sprint 6 — ATISS Layout Synthesis & Fine-tuning

**File:** `backend/python-scripts/atiss_layout.py`  
**Model:** ATISS (Autoregressive Transformers for Indoor Scene Synthesis) — MIT License  
**Paper:** https://arxiv.org/abs/2110.03937  
**Repo:** https://github.com/nv-tlabs/ATISS

### What is being done

OR-Tools (Sprint 5) is a constraint solver — it finds *a* valid placement, but not necessarily a *realistic* one. Two chairs placed perfectly legally might still look wrong for an office (e.g. facing a wall). ATISS is a learned model that has seen thousands of real interior scenes and generates placements that look natural.

ATISS works autoregressively:
1. A transformer processes the room boundary as a 2D mask
2. It generates objects one at a time: for each object it predicts `(category, position, size, orientation)` conditioned on all previously placed objects
3. Generation stops when an end-of-sequence token is produced or the object count limit is reached

**Integration:**
- `atiss_layout.py` loads ATISS weights from `models/atiss/` and calls `model.generate_boxes()` with the room mask and desired categories
- The output is a list of `{id, category, position, size, rotation, source: "atiss"}` placements compatible with the same API as Sprint 5
- Falls back to OR-Tools CP-SAT if weights aren't present

**Fine-tuning entry point:**
The `--finetune <data_dir>` flag runs ATISS training on 3D-FRONT format JSON scene files. When a dataset of real office layouts is assembled (e.g. from office floor plans or synthetic generation), this fine-tunes the model to understand office-specific spatial patterns (desks face windows, chairs cluster around conference tables, etc.)

### What this achieves
- Realistic, contextually appropriate furniture arrangements, not just collision-free ones
- A path to office-specific training: fine-tune on office floor plan data → model learns office conventions
- Architecturally separates "is this physically possible?" (OR-Tools) from "does this look like a real office?" (ATISS)

---

## Sprint 7 — Hunyuan3D-2 Integration

**File:** `backend/python-scripts/run_hunyuan3d.py`  
**AI adapter:** `backend/ai/hunyuan3d.js`  
**Model:** `tencent/Hunyuan3D-2` (Community License — commercial with attribution)  
**Weights size:** ~8 GB  
**Download:** `huggingface-cli download tencent/Hunyuan3D-2 --local-dir models/hunyuan3d`

### What is being done

Hunyuan3D-2 is Tencent's latest image-to-3D model. It differs from InstantMesh and TRELLIS in one key way: it includes a dedicated **texture baking stage** (`Hunyuan3DPaintPipeline`), producing textured meshes rather than single-colour PBR objects.

Pipeline:
1. **Background removal** via rembg, resize to 512×512
2. **Shape generation** — `Hunyuan3DDiTFlowMatchingPipeline` uses a DiT (Diffusion Transformer) with flow matching to generate a 3D shape from the image in ~30 steps
3. **Texture bake** — `Hunyuan3DPaintPipeline` takes the generated mesh and the original image and bakes a UV texture map onto it, producing a GLB with a proper texture atlas rather than a flat baseColorFactor
4. **Fallback PBR** — if texture bake fails (e.g. CPU memory limit), falls back to the average-colour PBR material used by TripoSR

**Fallback chain:** Hunyuan3D-2 → TRELLIS → TripoSR. If weights for any stage are missing, the next model in the chain is tried automatically.

### What this achieves
- Textured 3D objects that look photoreal in the xeokit viewer, not just solid-colour shapes
- A third high-quality reconstruction path, covering cases where TRELLIS and InstantMesh struggle (e.g. highly detailed upholstery patterns, woodgrain desks)
- The texture atlas is preserved in the IFC export — the `IfcTriangulatedFaceSet` geometry is accurate regardless of whether textures are present

---

## Sprint 8 — Polish & End-to-End Test Runner

**File:** `backend/python-scripts/test_pipeline.py`  
**Frontend:** TRELLIS and Hunyuan3D-2 added to model selection UI (`frontend/index.html`)  
**Pipeline service:** `backend/services/pipeline.js` updated with all 5 models

### What is being done

**Test runner (`test_pipeline.py`):**  
A comprehensive end-to-end test script that validates every layer of the pipeline. Running `python test_pipeline.py --model all` will:

1. Generate a synthetic test image (a simple chair silhouette drawn with Pillow) if no real image is provided
2. Run each model (TripoSR, InstantMesh, TRELLIS, Hunyuan3D-2) in sequence, measuring elapsed time and output GLB size
3. Take the first successfully generated GLB and run `saveIFC.py` against it, verifying the output IFC file is >1 KB (i.e. contains real geometry)
4. Run `classify_object.py` on the test image and verify it returns a classification result
5. Run `spatial_layout.py` with a 6×5m room and 3 furniture pieces, verifying all 3 are placed
6. Print a PASS/FAIL summary table and exit with code 0 (all pass) or 1 (any fail)

Each test is independent — a failure in one model does not abort the others.

**Frontend model UI:**  
The model selection sidebar in `frontend/index.html` now shows all 5 options:
- InstantMesh — Fast mesh generation (Zero123++ + LRM)
- StableFast3D — Stable & fast 3D
- TripoSR — High quality (single-view)
- TRELLIS — SLAT diffusion (MIT)
- Hunyuan3D-2 — Multi-view + texture bake

**Pipeline service registration:**  
`backend/services/pipeline.js` registers all 5 model adapters and routes `trellis` and `hunyuan3d` calls to their respective Python scripts via the AI adapters.

### What this achieves
- Any developer can run `python test_pipeline.py` and know within minutes whether the full stack is working
- CI-friendly: exit codes make it trivial to integrate into a GitHub Actions workflow
- Frontend reflects all available models — no hidden capabilities
- The pipeline service is the single source of truth for which models are available

---

## Dependency Installation Summary

```bash
# Python core (always required)
pip install ifcopenshell trimesh rembg Pillow numpy scipy

# Sprint 1 — InstantMesh
pip install diffusers transformers accelerate
huggingface-cli download TencentARC/InstantMesh --local-dir models/instantmesh

# Sprint 2 — TRELLIS
pip install trellis
huggingface-cli download microsoft/TRELLIS-image-large --local-dir models/trellis

# Sprint 3 — XKT export
npm install -g @xeokit/xeokit-convert   # gltf2xkt CLI

# Sprint 4 — Classification
pip install ultralytics   # YOLOv8

# Sprint 5 — Spatial layout
pip install ortools

# Sprint 7 — Hunyuan3D-2
pip install hunyuan3d diffusers
huggingface-cli download tencent/Hunyuan3D-2 --local-dir models/hunyuan3d
```

---

## What Phase 2 Achieves End-to-End

When all sprints are complete and weights are downloaded, the full workflow is:

1. **User uploads a photo** of an office chair
2. **Sprint 4** detects it as a `chair`, assigns `IfcChair` type and `textile_soft` material
3. **Sprint 1 or 2 or 7** reconstructs a complete 3D mesh (including chair legs, back, and seat underside) using multi-view diffusion
4. **Sprint 7** optionally bakes a photorealistic texture from the source photo
5. The GLB loads into xeokit via the existing Phase 1 viewer
6. User adds more objects (desk, bookshelf, plant)
7. **Sprint 5 or 6** automatically arranges all objects in the room without collisions, respecting ergonomic clearances
8. **Export fixes** send all objects with their real mesh geometry to `saveIFC.py`
9. **Sprint 3** converts the IFC to XKT for fast browser reloading
10. The user downloads a valid IFC4 file that opens in Revit with correct geometry, object types, and BIM properties

This is the target state of Phase 2.
