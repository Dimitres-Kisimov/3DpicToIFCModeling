# Pivot Blueprint — From Generative to Retrieval

**Date:** 2026-05-21
**Status:** Architecture decision. Supersedes the generative-first portions of `DEVELOPMENT_ROADMAP_PHASE2.md`.
**Goal of the project:** Take a 2D photo of office equipment → produce a clean 3D mesh → export to IFC (BIM-compliant) → visualize in xeokit so a room can be populated and laid out manually with drag/drop.

---

## 1. The problem we stumbled across

### What we tried
We built an image-to-3D pipeline using generative models: TripoSR first, then SAM2 + Humphrey smoothing + Poisson refinement, then TRELLIS. The plan was: photo → generative mesh → IFC.

### Why it fails for our use case
Testing on office chair photos exposed structural problems:
- **Asymmetric legs.** The four legs of a chair drift independently because the model has no symmetry constraint baked into its architecture. Each leg is generated from a noisy latent.
- **Noisy topology.** Small holes, non-manifold edges, discontinuities. The TRELLIS.2 model card explicitly documents these as known limitations requiring mesh post-processing.
- **Hallucinated back/underside.** A single photo contains zero information about hidden surfaces. The model fills them in by sampling from priors learned on Objaverse-like data; the guess is plausible but wrong in detail every time.
- **Non-deterministic output.** Same photo produces different meshes across runs. Unacceptable for a catalog where the same chair model should appear identically in every room it is dropped into.

### Why this is not fixable by switching models
This is a property of **single-view image-to-3D generation as a class of approach**, not a bug in any specific model:
- The reconstruction problem is mathematically ill-posed — you cannot reconstruct what was not in the input.
- All current top-tier models (TRELLIS.2-4B, Hunyuan3D-2.1, TripoSG, Hi3DGen, SF3D) hallucinate the same way.
- No model in 2026 has a learned office-furniture-specific symmetry prior.

### Why this matters here specifically
The company's requirements are:
1. **Catalog of office equipment** — chair, desk, monitor, cabinet, lamp, …
2. **IFC BIM compliance** — clean topology, correct named entity classes (IfcChair, IfcDesk).
3. **xeokit visualization with manual drag/drop** — same chair reused across many rooms.
4. **Free / commercially safe tools** — no paid memberships, no AGPL traps.

Generative AI gives us **unique, noisy, hallucinated meshes**. This use case needs **clean, repeatable, professional meshes**. Those are opposite optimization targets.

---

## 2. The pivot — retrieval + parametric fit

### New architecture
```
Photo of office object
    │
    ▼
[1] CLIP classifier  (already trained: models/clip_office/best_model.pt)
        → "office_chair" | "desk" | "monitor" | "lamp" | …
    │
    ▼
[2] DINOv2 image embedding  → nearest-neighbour search
        against a curated library of clean CAD office meshes
        → matched library item (clean, symmetric, watertight)
    │
    ▼
[3] Depth Anything V2  → estimate real-world dimensions (H/W/D in metres)
        → scale the matched mesh to fit the photo
    │
    ▼
[4] Material lookup from library metadata
        → PBR material (wood, fabric, metal, plastic)
    │
    ▼
[5] IfcOpenShell wraps the mesh with the correct IFC entity class
        → IfcChair / IfcDesk / IfcLamp / IfcFurniture
    │
    ▼
[6] Export GLB + IFC, load into xeokit
        → drag/drop, rotate, manually adjust
```

### Why this matches professional BIM
- Revit ships with parametric **families** for furniture. BIM modellers select from libraries; they do not generate from photos.
- BIMobject, RevitCity, 3D Warehouse, Sketchfab CC0 — the industry runs on libraries.
- IFC entity classes are defined assuming geometry is **known and clean**, not noisy.

### What we already have that fits
- ✅ CLIP fine-tuned classifier — first step of the retrieval pipeline (11 office categories trained).
- ✅ Depth Anything V2 — already in `backend/python-scripts/inference_base.py` (`estimate_metric_scale`).
- ✅ IFC export pipeline — `saveIFC.py`, `createIFCFurniture.py`.
- ✅ xeokit viewer + drag/drop infrastructure.
- ✅ Trimesh for geometry manipulation.
- ✅ SAM 2 for segmentation (Apache 2.0 — safe).

### What is missing
- ❌ A curated library of clean office furniture meshes.
- ❌ Image-to-mesh retrieval (embedding + nearest neighbour).
- ❌ Parametric scaling from estimated dimensions to the library mesh.
- ❌ Material metadata flow from library → IFC.

---

## 3. Free / commercial-safe tool stack

Every item below is verified free for commercial use without paid memberships.

### Datasets (CAD libraries)

| Source | License | Notes |
|---|---|---|
| **Amazon Berkeley Objects (ABO)** | CC BY 4.0 | 7,953 artist-made 3D meshes of real household + office products. PBR materials included. **Primary library.** |
| **3D-FRONT (Alibaba)** | Free for commercial use with registration | 18,800 interior designs including office subsets. Secondary source. |
| **Sketchfab CC0** | CC0 / Public Domain | Hand-pick clean office furniture; verify each item is CC0 (not CC-BY-NC). |
| Objaverse-XL | Mixed (per-object) | ⚠️ Skip — individual licenses vary; legally risky for distribution. |

### Models

| Model | License | Role |
|---|---|---|
| **CLIP (openai/clip-vit-base-patch32)** | MIT | Classifier + retrieval embedding |
| **DINOv2 (facebook/dinov2-base)** | Apache 2.0 | Higher-quality image embedding for retrieval |
| **Depth Anything V2 (Small)** | Apache 2.0 | Metric scale estimation (already wired) |
| **SAM 2 (facebook/sam2)** | Apache 2.0 | Object segmentation (already wired) |
| TRELLIS.2-4B | MIT | ✅ Kept only as fallback for objects not in the library |
| Hunyuan3D 2.1 | Tencent Community License | ⚠️ Skip — license has revenue/use restrictions |
| SAM 3 / SAM 3D | Not publicly released | ⚠️ Skip — not currently available |

### License watch list — things to remove or replace in current repo

| Tool currently in repo | License | Concern |
|---|---|---|
| **YOLOv8 (ultralytics)** in `yolov8n-seg.pt` | AGPL-3.0 | ⚠️ AGPL — if we distribute the project, the whole product becomes AGPL. SAM 2 (Apache 2.0) already covers the segmentation role; recommend replacing. |

### Geometry / IFC / Viewer (all free, commercial-safe)

| Library | License |
|---|---|
| Trimesh | MIT |
| IfcOpenShell | LGPL-3.0 (linkable from commercial software) |
| Open3D | MIT |
| xeokit-sdk | MIT |

---

## 4. Updated sprint plan

### Status of original Phase 2 sprints

| # | Title | Status under new blueprint |
|---|---|---|
| 1 | Real InstantMesh integration | ⏸ Deferred — generative, not catalog-aligned |
| 2 | TRELLIS integration | ⏸ Kept only as fallback path |
| 3 | XKT export + hosted viewer | 🔄 Still valid, still planned |
| 4 | Object classification (CLIP fine-tune) | ✅ Done — reframed as retrieval input |

### New sprints (replace old Sprints 4–6)

**Sprint 4.5 — Build the office furniture library** *(NEW)*
*Owner: Member 2 curates, Member 1 wires up*
- [ ] Download ABO `3dmodels` archive; filter to office furniture categories
- [ ] Hand-curate ~50 clean meshes covering the 11 categories the CLIP classifier already knows
- [ ] Verify each mesh is watertight and properly oriented
- [ ] Normalize all meshes to a canonical bounding box and origin
- [ ] Store metadata: category, dimensions (H/W/D in metres), PBR materials, target IFC class
- [ ] Output: `data/furniture_library/<category>/<id>.glb` plus `data/furniture_library/manifest.json`

**Sprint 5 — Image-to-mesh retrieval** *(replaces old Sprint 4)*
*Owner: Member 1*
- [ ] Pre-compute DINOv2 embeddings for every library mesh (use rendered views from multiple angles)
- [ ] Build retrieval pipeline: photo → DINOv2 embedding → cosine similarity → top-k library matches
- [ ] Confidence threshold: if top match score < 0.7, fall back to TRELLIS generative path
- [ ] Replace generative path in `inference_base.py:classify_object_clip` with retrieval call
- [ ] Member 2: test on 30 real office photos, log retrieval accuracy

**Sprint 6 — Parametric scaling** *(NEW)*
*Owner: Member 1*
- [ ] Use existing `estimate_metric_scale()` to get real-world H/W/D from the photo
- [ ] Scale the retrieved mesh's bounding box to match
- [ ] Preserve aspect ratios where the library mesh is more reliable than the estimate (e.g. monitor aspect)
- [ ] Write scaling validation tests

**Sprint 7 — Material & IFC metadata flow** *(NEW)*
*Owner: Member 1*
- [ ] Read PBR materials from ABO metadata
- [ ] Pass material info through GLB into IFC properties
- [ ] Ensure IFC entity class matches CLIP category (IfcChair, IfcDesk, IfcLamp, …)

**Sprints 5–6 (old) — Spatial positioning & ATISS** — Unchanged.
The retrieval pivot does not affect the spatial layout work; it improves the input quality (cleaner meshes, real materials, correct IFC classes feed the spatial solver better).

**Sprint 8 (old) — Polish, public demo** — Unchanged.

### What we stop investing in
- Making TRELLIS produce symmetric chair legs — not fixable at the model level.
- TripoSR refinement passes (SAM2 + Humphrey + Poisson — already abandoned in revert commit `345baf6`).
- Hunyuan3D integration — license risk.
- Manual YOLOv8 retraining — license risk; SAM 2 already covers segmentation.

---

## 5. Open question — long-tail handling

If a user uploads a photo of an item that is not in our library:
- **Option A** — Return the closest library match anyway. Lossy but always clean.
- **Option B** — Fall back to TRELLIS for that one object, mark it as "generated, low confidence."
- **Option C** — Refuse; ask the user to pick a match from a candidate list.

For a catalog-driven use case, A or C is probably right. To decide with the team before Sprint 5.
