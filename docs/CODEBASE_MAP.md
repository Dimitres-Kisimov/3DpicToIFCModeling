# Codebase Map — SCS Photo-to-BIM (full system picture)

Everything a new session (human or AI) needs to understand the whole system without re-exploring.
Distilled from a full codebase survey. Pair with `FABLE5_HANDOFF.md` (state + next steps),
`docs/PART2_ERGONOMICS_AND_ONE_APP_PLAN.md` (design), `docs/WORK_LOG_2026-07-06.md` (what we did).

## Two apps today (Part 2 merges them into one)
| | Port 3000 — Generator | Port 8000 — Room builder |
|---|---|---|
| Server | `backend/server.js` (Node/Express) | `backend/app_server.py` (Flask) |
| Frontend | `frontend/index.html` + `frontend/js/*` | `demo/app.html` + `demo/app.js` |
| Purpose | photo → 3D object → IFC | pick catalog items → lay out a room/building → IFC |
| Python | spawns scripts via child_process | imports scripts + subprocess |
| Shared | `backend/python-scripts/*`, `data/*`, xeokit viewer | same |

## Pipelines / subsystems and their files

**Generation (GPU):**
- `backend/ai/triposr.js` → `run_triposr.py` — TripoSR photo→3D (the "Detailed" engine). Includes the
  office-chair base graft (`graft_chair_base.py`) for chairs.
- `apiRoutes.js runDetectAndPlace()` → `run_detect_and_place.py` — the "Fast — from catalog" engine:
  DETR detect → Depth-Anything scale → DINOv2+FAISS retrieval → (fallback) TripoSR. Loads 3 models
  **per request** (the catalog-slowness cause). Retrieval gate at ~line 727 (`SCS_RETRIEVAL_THRESHOLD`).
- **GPU serialization:** `backend/services/gpuQueue.js` (concurrency 1) wraps both — never two on the 6 GB GPU.

**Mesh cleanup / graft / IFC:**
- `clean_and_optimize.py` — `clean_mesh()`: debris filter → **per-component** pymeshfix → Taubin → decimate.
- `graft_chair_base.py` — office-chair base graft (archetype of Part-1 work).
- `optimize_ifc.py` — IFC optimizer: clean unique meshes once → geometry instancing → precision round → zip.
  Auto-run on export in `backend/routes/exportRoutes.js`.
- `backend/services/ifcExporter.js` / `saveIFC.py` — scene objects → IFC.

**Layout / ergonomics engine (CPU) — the Part-2 core:**
- `rule_packs.py` — room types (office/living/workspace), ADA constants, per-category clearances,
  functional groups (chair→desk, monitor→desk), **A1 archetypes + ANTHRO + placement_profile()** (new).
- `spatial_layout.py` — CP-SAT solver `_solve_layout_ortools()`: 10 cm grid, footprint+clearance
  no-overlap, fixed obstacle keep-outs, wall-affinity objective, **0/90° rotation only** (30 s cap),
  `_fallback_stack_layout()` on infeasible. Entry `layout_room(room, objects, obstacles)`.
- `build_room_scene.py` — `_resolve_layout()`: solves free objects, then anchors children
  (`in_front`/`on_top`/`beside`); chair facing via mesh backrest (`_chair_forward_xz`, ~line 179);
  feasibility check ~line 243. Builds `schedule.json` + `scene.glb`.
- `build_room_ifc.py` — schedule → IFC (IfcProject/Site/Building/Storey/Space + IfcFurniture);
  currently **drops** functional relationships (A6 will persist them).
- `populate_building.py` — building-scale: loads real IFC (`sample_buildings/Duplex_Architecture.ifc`),
  extracts IfcSpace rooms + obstacles (`footprint_rects()` — pillars/columns/doors), `smart_furnish()`,
  runs the solver per room. This is where **A3b** building-obstacle extraction is generalized.
- `make_scene_spec.py` — photo folder → scene spec JSON.

**Catalog:**
- `catalog.py` — lists categories/items from `data/mesh_library_abo/manifest.json` (ABO meshes) +
  `data/generated_assets/manifest.json` (user uploads). `list_items()`, `_manifest()` (cached).
- `data/mesh_library_abo/` (ABO meshes + thumbnails), `data/mesh_library/` (procedural fallback,
  `build_mesh_library.py`), `data/generated_assets/` (user-added, `upload_generated`).

**Frontend (:3000):** vanilla JS modules on `window.*`. `xeokitViewer.js` (viewer, applies rotation
`[180,0,90]` to generated meshes), `inventory.js`, `transformControls.js` (numeric/keyboard move —
**no 2D editor, no collision**), `exporter.js` (`prepareSceneForExport` → `/export/ifc`). Object model:
`{id, glbPath, position, rotation, scale, name, ifcClass, category, dimensions}`.

## Object universe (46 types) — dimensions & sources
- CLIP→IFC map: `inference_base.py:35` (`_IFC_LABEL_MAP`) + height priors `:214`.
- COCO→SCS map: `run_detect_and_place.py:63`. Catalog ergonomic dims: `catalog.py:26` (`CATALOG_META`).
- Asset library dims: `build_asset_library.py:33`. Real dims come from the depth model (generated) or
  measured mesh extents (ABO/library). **A1 groups all of these into 8 archetypes** so rules cover any object.

## Key gaps the ergonomics engine must close (from the survey)
Item-spacing exists, but **not people-space**: no enforced circulation aisles (rule_packs defines
`min_aisle` but the solver ignores it), no task/interaction envelopes (legroom, seat pull-out, door
swing), 0/90° rotation only, all-or-nothing feasibility (can silently drop items), relationships lost
in IFC, 2D-AABB collision only. Part-2 workstreams A2–A6 address each.

## Durable project facts (context)
- Commercial-safe licensing posture; TripoSR (MIT) is the local generator; SAM3D/TRELLIS/TripoSG are
  stronger but need more VRAM than the 6 GB dev card (cloud/GEX44 only).
- Prod hosting pick: Hetzner GEX44 (GPU). Building population targets a LOADED architectural IFC
  (Duplex), not a self-authored one.
- Other reference docs in repo: `docs/OPTIMIZATION_GUIDE.md`, `OPTIMIZATION_WORK_AND_VISUALS.md`,
  `SCS_MONOGRAPH_Photo_to_IFC.md`, `REPORT_IFC_to_3D_and_Progress_2026-07-01.md`.
