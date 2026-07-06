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

---

## Localhost comparison / visual pages (for the paper — each demonstrates an issue)

All served by the app under `frontend/` (open at `http://localhost:3000/<page>`). Grouped by the
research point they make. Use these as figures/evidence when writing up the pipeline's issues.

### Reconstruction quality: model choice > post-processing
| Page | Compares | Issue it demonstrates |
|---|---|---|
| `chair_compare.html` | ① TripoSR raw · ② TripoSR cleaned · ③ SAM 3D (F=0.63) | Quality is dominated by the **generative model**, not cleanup — ①→② (cleanup) is tiny, ②→③ (model) is the big jump. Argues model selection over mesh cleanup as the primary lever. |
| `four_way.html` | ① raw · ② IFC-optimized · ③ catalog (SAM3D) · ④ mesh-optimized | **Fidelity-vs-cleanliness & catalog-vs-generated** tradeoff: optimization preserves the *photographed* chair; catalog retrieval is clean but a *different* chair. |
| `four_way_all.html` | same 4-way across 10 furniture items (dropdown) | The same tradeoff **generalizes across all furniture types**, not just chairs. |

### Mesh → IFC optimization (size/faces)
| Page | Compares | Issue it demonstrates |
|---|---|---|
| `ifc_compare.html` | bed IFC before (150k f, 5.1 MB) vs after (15k f, 420 KB) | **~90% fewer faces, ~92% smaller**, still valid IFC4 — IFC embedding needs decimation. |
| `chair_final.html` | one optimized chair (85.5k→15k f, 1.5 MB→264 KB) | Debris-removal + smoothing + decimation makes a raw mesh **BIM-ready** (−82% f, −83% size). |
| `gallery3d.html` | 10 optimized items, per-item face reduction (50k–126k→~15k) | A uniform **~15k-face / ~264 KB budget**; the already-small lamp (12.5k→12.4k) shows the **decimation floor**. |
| `optimize_test.html` | numbers table of mesh+IFC optimization across items | Quantitative before/after (faces, size) — the results table. |
| `optimize_visual.html` | bar charts of face/size reduction | Visual quantitative summary of the optimization gains. |

### Office-chair base graft (Part 1 contribution)
| Page | Compares | Issue it demonstrates |
|---|---|---|
| `graft_compare.html` | raw fragmented base vs grafted clean 5-star base | TripoSR **fragments the thin swivel wheelbase**; a hybrid generated-mesh + parametric-CAD-part graft repairs it. |
| `legs_compare.html` | base radius 0.55 (too wide) / **0.42** (fits) / 0.34 (stubby) | **Ergonomic proportioning** of the procedural base to the seat footprint. |
| `smooth_compare.html` (3D) / `smooth_static.html` (images) | raw · Taubin ×16 · ×40 | **Smoothing tradeoff**: big jump raw→graft, marginal ×16→×40 — the *face budget*, not smoothing, is the limiting factor. |

### Room / building population (Part 2 context)
| Page | Shows | Issue it demonstrates |
|---|---|---|
| `empty_building_viewer.html` | empty Duplex shell (21 rooms, 113 walls, 14 doors, 24 windows) | The **architectural IFC input** before furnishing. |
| `building_viewer.html` / `populated_building_viewer.html` | whole populated building (furniture across rooms) | **Building-scale ergonomic population** output — the Part-2 target. |

---

## Algorithms catalog ("all the algos")

Every algorithm in the pipeline, with its file and the problem it solves.

**Perception / generation (GPU):**
- **TripoSR** (`run_triposr.py`) — single-image→3D (transformer triplane field → marching cubes). MIT. Primary local generator.
- **SAM2** (`run_triposr.py`) — foreground segmentation mask for the input photo.
- **DETR ResNet-50** (`run_detect_and_place.py`) — object detection / bounding box.
- **Depth Anything V2 (metric)** (`inference_base.py`) — monocular metric depth → real-world scale.
- **CLIP (zero-shot + fine-tuned)** (`inference_base.py`) — object classification → IFC class/category.
- **DINOv2 + FAISS** (`run_detect_and_place.py`) — image-embedding retrieval against the catalog (kNN).

**Mesh processing (CPU):**
- **Connected-component debris filter** (`clean_and_optimize._debris_filter`) — drop floating fragments/spikes.
- **pymeshfix / Attene MeshFix, per-component** (`clean_and_optimize.clean_mesh`) — watertight repair without collapsing multi-part objects.
- **Taubin smoothing (λ/μ)** (`clean_and_optimize`, `graft_chair_base`) — volume-preserving denoise.
- **Quadric decimation (Garland-Heckbert)** via `fast_simplification` — reduce to a face budget.
- **Voxel solidify + marching cubes** (`clean_and_optimize._voxel_solidify`) — fuse detached parts into one watertight solid.
- **PBR baseColorFactor capture/apply** (`clean_and_optimize`) — preserve colour (xeokit ignores vertex colours).

**Office-chair base graft** (`graft_chair_base.py`):
- **Up-axis detection** (argmax of bbox extents); **base-region cut** (bottom 20%).
- **Parametric 5-star base** construction (hub + gas column + 5 spokes + 5 casters).
- **Voxel-fuse + AABB refit** — one solid, corrected for `marching_cubes` index-space scale.
- **Anthropometric base sizing** (`SCS_BASE_RADIUS_FRAC` 0.42 × seat footprint).

**IFC** (`optimize_ifc.py`, `saveIFC.py`):
- **IfcTriangulatedFaceSet** build (CoordList + 1-based CoordIndex).
- **Geometry instancing** via geometry-hash dedup (`_geo_hash`/`_repoint`) — store identical meshes once.
- **Coordinate precision rounding** (~0.1 mm) — smaller STEP text.
- **IFC-zip** (gzip).

**Layout / ergonomics** (`spatial_layout.py`, `rule_packs.py`, `build_room_scene.py`, `populate_building.py`):
- **CP-SAT constraint solver (OR-Tools)** — discretised (10 cm) non-overlap furniture placement.
- **AddNoOverlap2D** on clearance-padded footprints + **fixed obstacle keep-outs** (columns/doors).
- **Wall-affinity objective** — minimise distance-to-wall for perimeter/tall/elongated items.
- **Geometry-derived clearance/perimeter fallbacks** — item-agnostic for unknown catalogue objects.
- **Anchoring relations** (`in_front`/`on_top`/`beside`) + **chair facing** via mesh backrest (`_chair_forward_xz`).
- **Archetype resolution + anthropometric interaction zones** (`rule_packs.placement_profile`, A1 — new).
- **Building-obstacle extraction** (`populate_building.footprint_rects`) — columns/walls/doors as keep-outs.
- **Neufert / Panero-Zelnik / ADA rule packs** — area/person, aisle widths, clearances, turning circle.
- *(planned A2–A4)* interaction-zone reservation, circulation flood-fill (walkable path), per-item feasibility.

**Efficiency:**
- **GPU job serialization queue** (`backend/services/gpuQueue.js`) — concurrency 1; prevents 6 GB OOM.
- **Retrieval threshold gate** (`run_detect_and_place`, `SCS_RETRIEVAL_THRESHOLD`) — catalog vs generate.
- **Manifest caching** (`catalog.py._manifest`).
