# SCS Photo-to-BIM — Final Project Documentation

**Project:** 3D Picture to IFC Modeling (SCS Studio)
**Repository:** `Dimitres-Kisimov/3DpicToIFCModeling`
**Document status:** Draft for finalization once the application is deployment-ready.
Sections marked **PENDING** will be completed after the 2026-07-11 A100 pod run.
**Date of this draft:** 2026-07-11
**Audience:** SCS stakeholders (management and legal) and future developers.

Every substantive claim in this document cites the repository file it is drawn from.
No number in this document is estimated by the author of this draft; all figures are
reproduced from the cited measurement logs, benchmark reports, and source files.

---

## 1. Executive Summary

SCS Studio converts a **single 2D photograph of a piece of office furniture into a
3D model and then into an IFC file** — the vendor-neutral Building Information
Modeling (BIM) format that opens in Revit, ArchiCAD, BIM Vision, and FreeCAD. The
entire system is **one desktop application**: a Node.js server on `localhost:3000`
serving three workspaces over a single shared 3D viewport — *Generate object*
(photo → 3D → BIM-classified mesh), *Build a room* (catalog furniture + an
ergonomics-aware layout solver), and *Building* (load a real architectural IFC and
auto-furnish it room by room) (`README.md`, `frontend/index.html`,
`frontend/js/shell.js`).

The core architectural decision, adopted 2026-05-21 and validated repeatedly by
measurement since, is **retrieval-first with a generative fallback**
(`deliverable/docs/TECHNICAL_REPORT_SCS.md` §4.6): when a photographed object can be
matched against the Amazon Berkeley Objects (ABO) catalog of real, artist-authored
product meshes, the system returns the clean catalog mesh; only when no match exists
does it fall back to generating a mesh from the photo with the TripoSR neural
network. The reason is quantitative — in the project's own five-generator cloud
benchmark, the real catalog mesh scores **1.000** by definition while the best
generative model available under a commercially safe licence scores **0.393** on the
same shape-accuracy metric, a ~2.5× gap
(`deliverable/CLOUD_BENCHMARK_FINDINGS.md`).

Everything runs on **consumer hardware**: the development and reference machine is
an RTX 4050 Laptop GPU with 6 GB of VRAM (`README.md` "Requirements",
`docs/WORK_LOG_2026-07-06.md`). Only the photo→3D generation step needs the GPU;
room layout, building population, IFC export, and the web viewer are CPU/WebGL and
run anywhere (`docs/WORK_LOG_2026-07-06.md` "Hardware / deployment findings"). The
full model stack is local — no cloud API is called at runtime, no customer photo
leaves the machine (`deliverable/docs/TECHNICAL_REPORT_SCS.md` §3.6).

The project has additionally produced: a **licence-audited model selection funnel**
that eliminated several popular models that "look free but aren't"
(`docs/HUGGINGFACE_MODEL_NARROWING.md`); a **quality-engineering layer** ("repair
packs") that turns raw generative meshes into light, watertight, IFC-valid solids,
proven on 170 internet photos (`benchmark/README.md`); and a **five-model cloud
benchmarking program** with full reproduction manuals for every model tested
(`deliverable/manuals/README.md`).

---

## 2. The Problem and the Approach

### 2.1 The problem

SCS operates in the BIM sector. The deliverable is a system that lets SCS or its
clients populate virtual building models with 3D representations of office
furnishings **by photography rather than manual modeling**: upload a photo of a
chair, get back (a) a 3D mesh, (b) an IFC4 file in which the mesh is wrapped as a
typed BIM entity (`IfcChair`, `IfcDesk`, `IfcLamp`, …), and (c) a web-viewable scene
where the object can be dragged into a room
(`deliverable/docs/TECHNICAL_REPORT_SCS.md` §1.1).

### 2.2 Why single-photo generation alone cannot solve it

The project's first phase built exactly the obvious pipeline — TripoSR single-image
3D reconstruction end to end — and then measured it honestly. Four systematic
failure modes emerged, documented in `deliverable/docs/TECHNICAL_REPORT_SCS.md`
§3.2:

1. **Asymmetric structural elements** — four identical chair legs come out drifting
   independently in length and angle, because single-view generators have no
   symmetry prior.
2. **Hallucinated hidden surfaces** — a front photo carries zero information about
   the back; the model fills it in plausibly but wrongly, every time.
3. **Non-determinism** — diffusion-based generators produce a different mesh on
   every run for the same photo, which breaks a catalog workflow where the same
   chair must appear identically in many rooms.
4. **Absent PBR materials and absent metric scale** — flat averaged colour, no
   real-world dimensions.

These are properties of the *class* of approach, not bugs in one model
(`TECHNICAL_REPORT_SCS.md` §3.3). The single-view ceiling was later quantified
directly: TripoSR reconstructions of known ABO chairs achieve **precision ~0.81 but
recall ~0.09** — the visible surface is captured fairly accurately, but only ~9% of
the true surface is recovered, because the back and sides were never in the photo
(`docs/ACCURACY_RESULTS.md`).

### 2.3 The retrieval-first pivot

On 2026-05-21 the project pivoted to a **retrieval architecture**
(`TECHNICAL_REPORT_SCS.md` §4.6): instead of asking *"what is the 3D shape of this
object?"*, ask *"which item in a curated library is this object?"*. The pipeline
becomes: photo → detection → segmentation → DINOv2 image embedding →
nearest-neighbour lookup (FAISS) against pre-embedded renders of the **Amazon
Berkeley Objects** library (7,953 artist-authored meshes, CC-BY-4.0;
`TECHNICAL_REPORT_SCS.md` §4.6) → the matched real mesh, scaled to metric
dimensions estimated by a monocular depth model.

Retrieval fixes all four failure modes at once for in-catalog items — the library
mesh is symmetric, complete on all sides, has authored materials, and is
deterministic (`TECHNICAL_REPORT_SCS.md` §2.3). This is also how industrial BIM
actually works: Revit families, BIMobject, RevitCity — catalog selection, not
generation. The SCS-distinctive value is automating the *selection*
(`TECHNICAL_REPORT_SCS.md` §1.1).

The generative path (TripoSR, MIT licence) is retained as the **fallback for items
missing from the catalog**, followed by the repair-pack quality layer described in
§5 of this document. The retrieval-vs-generate decision is a configurable
similarity threshold (`SCS_RETRIEVAL_THRESHOLD`,
`backend/routes/apiRoutes.js`; gate described in `docs/CODEBASE_MAP.md`).

---

## 3. System Architecture

### 3.1 One application

Since 2026-07-06 the system is **one app**: `npm start` → `http://localhost:3000`.
The former Flask room-builder on port 8000 is retired; Node is the single front
door (`README.md`). The Express server (`backend/server.js`) serves the frontend
and exposes the API routes; Python is invoked as subprocesses for all AI and
geometry work (`backend/services/pythonBridge.js`, `docs/CODEBASE_MAP.md`).

Three workspaces share one 3D viewport (`frontend/index.html`,
`frontend/js/shell.js`):

- **📷 Generate object** — photo upload → engine choice → 3D model → BIM
  classification → IFC export. Every generated object **auto-registers into the
  room catalog** with an "OURS" badge and a rendered thumbnail (the "B3 loop":
  `autoRegisterGenerated()` in `backend/routes/apiRoutes.js`).
- **🛋️ Build a room** — pick furniture (515 ABO meshes plus the user's own
  generated objects); a **people-aware CP-SAT solver** places items with legroom,
  door-swing and bed-access zones, 4-way facing, back-to-wall preference, and
  circulation checks — or reports honestly, per item, that there is *not enough
  space*. A **2D floor-plan editor** allows exact X·Z·rotation placement with live
  collision and live 3D sync; export is CSV / GLB / one optimized IFC
  (`README.md`).
- **🏢 Building** — load a real architectural IFC, review per-room smart
  suggestions, populate around the building's own walls/beams/columns, drag pieces,
  save the GLB (`README.md`, `backend/routes/buildingRoutes.js`).
- **▶ Demo run** — a one-click, presentation-ready demo room (`README.md`,
  `frontend/index.html`).
- **🔬 Research** — a hub page (`frontend/hub.html`) linking every benchmark,
  before/after comparison, and gallery the project has produced.

### 3.2 The generation pipeline (GPU)

Two engines are exposed in the UI's engine selector (`frontend/index.html`,
`#engineSelect`):

- **"Detailed — new 3D model"** — TripoSR (`backend/ai/triposr.js` →
  `backend/python-scripts/run_triposr.py`): transformer triplane reconstruction,
  marching cubes at 256³ on GPU, then post-processing (component debris filter,
  orientation fix, Laplacian smoothing, PBR base-colour material) (`README.md`
  "How it works").
- **"Fast — from catalog"** — the retrieval engine
  (`backend/python-scripts/run_detect_and_place.py`): DETR detection →
  Depth Anything V2 Small metric scale → DINOv2 + FAISS retrieval against the
  catalog → TripoSR only as fallback (`docs/CODEBASE_MAP.md`).

**Segmentation ladder.** Foreground isolation in the TripoSR path tries **SAM 2.1
(hiera-tiny checkpoint) first and falls back to rembg (U²-Net)** if SAM2 fails; the
segmenter can be forced via `SCS_TRIPOSR_SEGMENTER` for A/B testing
(`backend/python-scripts/run_triposr.py`, functions `_rembg_foreground` and the
SAM2 branch).

**GPU safety on a 6 GB card.** All GPU jobs pass through a **concurrency-1 queue**
(`backend/services/gpuQueue.js`): every generation is a fresh Python subprocess
that fully releases VRAM on exit, so jobs run one at a time and iterative
multi-object generation cannot OOM the card. Verified on the RTX 4050: two
simultaneous generation requests serialized, peak VRAM 5.47 GB of 6.14 GB, both
succeeded (`docs/WORK_LOG_2026-07-06.md`). An analogous CPU queue bounds heavy
building jobs (`backend/services/cpuQueue.js`).

**Pinned Python.** The pipeline runs against a pinned interpreter with the required
geometry stack (trimesh / ifcopenshell / pymeshfix):
`C:\Users\dimik\AppData\Local\Python\pythoncore-3.14-64\python.exe`
(`docs/WORK_LOG_2026-07-06.md` "Critical facts"). Python 3.14 required patching
TripoSR's iso-surface extraction to `skimage.measure.marching_cubes` because
`torchmcubes` has no wheels for it (`README.md` "Known issues",
`backend/triposr/tsr/models/isosurface.py`).

**Result caching.** An image-hash cache means the same photo detected twice costs
zero seconds (`_detectCache` in `backend/routes/apiRoutes.js`).

### 3.3 Mesh quality and IFC export (CPU)

- `backend/python-scripts/clean_and_optimize.py` — debris filter → per-component
  pymeshfix watertight repair → Taubin smoothing → quadric decimation
  (`docs/CODEBASE_MAP.md`).
- `backend/python-scripts/graft_chair_base.py` — the office-chair **base graft**:
  TripoSR fragments thin swivel bases into ~500 pieces; the graft cuts the broken
  base and attaches a clean parametric 5-star base sized to the seat footprint
  (radius fraction 0.42 of the seat footprint, chosen by comparison —
  `frontend/legs_compare.html`, `docs/CODEBASE_MAP.md`). Toggle in the UI
  (`frontend/index.html`, `#graftBaseChk`).
- `backend/python-scripts/repair_packs.py` — the generalized archetype repair layer
  (see §5).
- `backend/python-scripts/saveIFC.py` — the IFC exporter: a real ifcopenshell
  **IFC4** file with the standard hierarchy (Project → Site → Building → Storey),
  SI units in metres, and each object's actual mesh written as an
  `IfcTriangulatedFaceSet` under a typed entity; meshes are decimated to at most
  8,000 faces for export (`saveIFC.py` docstring,
  `deliverable/docs/TECHNICAL_REPORT_SCS.md` §4.2).
- `backend/python-scripts/optimize_ifc.py` — IFC optimizer, auto-run on export:
  geometry instancing via geometry-hash dedup, ~0.1 mm coordinate precision
  rounding, IFC-zip. Measured effect on a bed IFC: 150k → 15k faces, 5.1 MB →
  420 KB (~92% smaller), still valid IFC4 (`docs/CODEBASE_MAP.md`,
  `frontend/ifc_compare.html`).

### 3.4 Layout and building-scale features (CPU)

- `backend/python-scripts/rule_packs.py` — room types, ADA/Neufert/Panero-derived
  clearance constants, functional groups (chair→desk, monitor→desk), placement
  archetypes and anthropometric interaction zones (`docs/CODEBASE_MAP.md`).
- `backend/python-scripts/spatial_layout.py` — the **OR-Tools CP-SAT solver**:
  10 cm grid, footprint + clearance no-overlap, fixed obstacle keep-outs,
  wall-affinity objective (`docs/CODEBASE_MAP.md`).
- `backend/python-scripts/build_room_scene.py` / `build_room_ifc.py` — object table
  → solved layout → `scene.glb` + IFC4 with spatial hierarchy and typed furniture
  (`docs/FINDINGS.md`).
- **Building registry** (`backend/routes/buildingRoutes.js`): any-IFC upload
  pipeline — *sniff, probe, register, prepare* — with per-building geometry caching
  (first scan pays; repeats are solver-only), timeouts scaled to the probed product
  count, and per-building scratch directories. Bundled samples plus up to 25
  uploads.
- **Building population** (`backend/python-scripts/populate_building.py`): reads
  every `IfcSpace` of a loaded architectural IFC, extracts intruding obstacles
  (walls, beams, columns, stairs) and door keep-clear zones, and runs the CP-SAT
  solver per room. Verified on the bundled Duplex (21 rooms): **8 rooms furnished,
  0 clashes**, pure CPU (`README.md` "Building-Scale Population"). A four-building
  fleet comparison (real IFCs from 0.2 MB to 47 MB) is documented at
  `frontend/fleet.html` (linked from `frontend/hub.html`).

### 3.5 Viewers

- **xeokit SDK v2.6.108** (WebGL, installed locally via npm) is the application's
  3D viewport — GLB loading, orbit/pan/zoom, object picking
  (`README.md` "Stack", `frontend/js/xeokitViewer.js`). A known constraint: xeokit
  ignores `COLOR_0` vertex colours, so object colour is carried as a glTF PBR
  `baseColorFactor` material (`README.md` "Known issues").
- **three.js (0.160)** powers the research-side viewers, e.g. the benchmark
  candidate visualizer (`benchmark/visualizer.html`) that shows every mesh variant
  of an item side by side in interactive 3D with winner selection.
- Building viewers: `frontend/{empty,populated,building}_building_viewer.html`
  (`README.md`).

---

## 4. Model Selection Journey — the HuggingFace Narrowing Funnel

The project's model choices were not ad hoc; they are the output of a documented
six-stage funnel (`docs/HUGGINGFACE_MODEL_NARROWING.md`, which indexes the four
underlying source documents).

**Stage 1 — raw sweep (2026-04-29).** The entire HuggingFace `image-to-3d` tag,
ranked by trending/likes/downloads. Recorded selections with their popularity
numbers: TRELLIS (MIT, 600+ likes), InstantMesh (Apache-2.0, 14k+ downloads/mo),
Hunyuan3D-2 (74k+ downloads/mo, 1,750 likes — the tag's most downloaded, flagged
for licence review), honourable mention Stable Fast 3D (`TEAM_ROADMAP.md`,
`DEVELOPMENT_ROADMAP_PHASE2.md`).

**Stage 2 — strict commercial-licence + hardware funnel → 20 candidates
(2026-06-06).** Five inclusion criteria (verifiable licence on the model card;
commercial grant SCS can meet; fits the 8 GB dev box natively or via offload;
addresses a pipeline task) and four exclusion rules (AGPL/GPL; CC-BY-NC;
research-only; model cards that disclaim deployment in body text even under a
permissive file licence). Every licence claim quoted **verbatim from the model
card**. Output: 10 cross-pipeline + 10 detection candidates (`MODEL_SURVEY_SCS.md`,
`deliverable/docs/TECHNICAL_REPORT_SCS.md` §6).

The **licence kill-list** produced at this stage — models that look free and are
not (`docs/HUGGINGFACE_MODEL_NARROWING.md`; verbatim clauses in
`TECHNICAL_REPORT_SCS.md` §6.4 and `MODEL_SURVEY_SCS.md` §7):

| Model | Why rejected |
|---|---|
| **Hunyuan3D-2** (Tencent) | Licence text: *"DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"* — SCS could not deploy to EU/UK clients at all; plus a 1M monthly-active-user cap and an output-binding clause forbidding use of outputs to improve any other AI model (which would block feeding generated meshes into the retrieval index). Triple-disqualified; never even benchmarked, since a local run in the EU is itself a violation risk (`docs/HUGGINGFACE_MODEL_NARROWING.md` Stage 5). |
| **Stable Fast 3D** (Stability AI) | Stability Community License — free only below **US$1M annual revenue**; above it an enterprise licence is required. Kept for benchmarking only. |
| **Wonder3D** | CC-BY-NC — non-commercial. |
| **Depth Anything V2 Base / Large** | CC-BY-NC-4.0. **Only the Small variant is Apache-2.0** — a silent trap, since a routine "upgrade for quality" would void commercial use. The pipeline pins Small (`backend/python-scripts/inference_base.py`). |
| **YOLOv8 / Ultralytics** | AGPL-3.0 — strong copyleft that would force SCS application code open. Replaced by SAM 2.1 (Apache-2.0); the `yolov8n-seg.pt` weights file flagged in the audit has been removed from the repository tree (verified absent as of this draft). |
| **OpenAI CLIP** (as a deployed model) | Model card: *"Any deployed use case of the model … is currently out of scope"* despite MIT file licence — legal ambiguity; SigLIP 2 / DINOv2 preferred. |

**Stage 3 — adopted into production (the retrieval-first spine).** DINOv2-Large +
ABO catalog (retrieval), SAM 2.1 (segmentation), Depth Anything V2 **Small**
(metric scale), TripoSR (generative fallback), CLIP fine-tune (classification; a
13,752-image, 11-category fine-tune documented in `TECHNICAL_REPORT_SCS.md` §4.5).
Rationale: the retrieval framing solves colour, material, dimension, and
determinism at once — no generative model surveyed does
(`docs/HUGGINGFACE_MODEL_NARROWING.md`, `MODEL_SURVEY_SCS.md` §8).

**Stage 4 — the measured 5-AI bake-off (H200, 2026-06-30 → 07-01).** See §6 below.

**Stage 5 — still untested, and why.** TRELLIS.2-4B (manual pre-written,
`deliverable/manuals/TRELLIS2.md`; needs ≥24 GB — next pod run); Stable Fast 3D
(infer script ready; benchmark-only due to the licence cap); SAM 3 / SigLIP 2 /
Grounding DINO (shortlisted, runnable locally); the detection finalists (OWLv2,
Florence-2, OneFormer — benchmark script delivered, awaiting a labelled SCS photo
set); Hunyuan3D-2 permanently untested on licence grounds
(`docs/HUGGINGFACE_MODEL_NARROWING.md`).

**Stage 6 — post-generator quality layer (2026-07-11).** The archetype repair
packs (§5), which are generator-agnostic and apply behind any engine above.

---

## 5. Quality Engineering — the Repair-Packs Layer

Raw single-view generative output is structurally unfit for BIM: 70k–200k+ faces,
fragmented thin supports, non-watertight shells. The **repair packs**
(`backend/python-scripts/repair_packs.py`) generalize the proven office-chair
base-graft recipe — *keep what the generator does well (body shape, colour);
rebuild what single-view reconstruction structurally cannot (thin supports,
symmetry, floor contact)* — to **all 17 furniture categories** in the app's picker.

### 5.1 Design

Every CLIP label or picker category resolves to one of **7 repair archetypes**,
each running a hand-tuned stack of **8 guarded CPU stages** (a failing stage falls
back rather than corrupting the mesh) (`repair_packs.py` module docstring,
`benchmark/README.md`):

| Archetype | Categories | Signature fixes |
|---|---|---|
| legged | table, desk, coffee/side table, stool, chair, bench | strict symmetry; support health check → evidence-driven rebuild |
| swivel_seat | office_chair | drift removal + the proven 5-star base graft |
| boxy | cabinet, filing_cabinet, bookshelf, wardrobe, dresser | crisp-edge smoothing, plinth rebuild |
| upholstered | sofa, couch, armchair, bed | Taubin ×14 fabric softness, plinth |
| panel | mirror, picture_frame, clock, monitor, tv | tanh thickness clamp — flat wall slabs |
| slender | lamp, planter, plant | thin-part-protecting filters, no forced symmetry |
| prop | laptop + anything unknown | safe universal clean (fallback for any object) |

The universal stage sequence: up-aware debris filter (keeps legs/poles) →
per-component pymeshfix watertight repair → **detected-plane symmetry snap**
(axis+offset scored by chamfer distance — no hard-coded X=0 assumption) → Taubin
smoothing → decimation to a 10–15k face budget → panel flatten → final crumb-sweep
+ watertight heal → support rebuild (only when the bottom is actually broken — an
intact tripod or pedestal passes the health check) → flush floor contact
(`benchmark/README.md`, `repair_packs.py`).

Operational knobs: `SCS_REPAIR_PACKS=0` (kill-switch), `SCS_REPAIR_ARCHETYPE`
(force, used by the office-chair UI toggle), `SCS_REPAIR_UP_AXIS` (default 0 = X;
TripoSR's native frame is X-up, verified empirically) (`repair_packs.py`).

### 5.2 The 170-item proof (2026-07-11)

A standalone A/B benchmark (`benchmark/README.md`) proved the layer on
**170 unique internet photos** — 10 gallery lists × 17 categories, none from the
catalog, all CLIP-validated, all timestamped. Campaign: 2026-07-11 05:13 → 08:00
local, **170/170 generated, 0 failures**, RTX 4050 Laptop 6 GB, TripoSR loaded
once, ~55 s/item. Headline numbers:

| Metric | TripoSR today | With repair packs |
|---|---|---|
| Mean faces | 111,143 | **12,039** (9.2× lighter) |
| Watertight solids | fragments individually closed | **91%** fully closed objects |
| Broken bases rebuilt | shipped broken | **48** (evidence-driven: legs at detected stub positions / tripod / trestle / pedestal / plinth) |
| Silhouette IoU vs photo | 0.662 | **0.646** (shape preserved while restructuring) |
| IFC spot-proofs | — | **20/20 valid IFC4** with real mesh geometry, via the app's own `saveIFC.py` |

Honest limits, recorded in the same report: clean single-object photos improve
dramatically (office chairs, stools, clocks, cabinets); angled or cluttered
museum-style shots produce blobby bodies — the repair fixes their *structure*
(solid, grounded, light, IFC-valid) but cannot invent detail the single view never
contained (`benchmark/README.md`).

The benchmark also caught and fixed real engineering bugs: an axis swap in support
building (legs built in local Z-up landed 90° off in plan — the builder now works
in world coordinates), and decimation/cut operations opening cracks — cured by a
final `_finalize` stage restoring watertightness (`benchmark/README.md`
"Engineering notes"). Results are browsable as a self-contained gallery
(`benchmark/` served on `:8000`, with a three.js candidate visualizer for picking
winners per item).

---

## 6. Benchmarking Program

### 6.1 The H200 five-generator study (2026-06-30 → 07-01)

To ground the retrieval-first decision in numbers, five single-image→3D generators
were run on identical inputs (10 furniture types, one 2D front-view image each) and
scored against the real ABO catalog mesh with the same scorer — **Chamfer distance
+ F-score@0.02 after multi-seed ICP alignment, seed 42**
(`deliverable/CLOUD_BENCHMARK_FINDINGS.md`, `docs/HUGGINGFACE_MODEL_NARROWING.md`
Stage 4, metric definition in `docs/ACCURACY_RESULTS.md`). Cloud GPU: RunPod H200
(143 GB); TripoSR baselines ran locally on the 6 GB RTX 4050.

| Model | Licence | Mean F@0.02 | Avg time/image |
|---|---|---|---|
| **ABO mesh (ground truth)** | CC-BY-4.0 | **1.000** | — |
| **TripoSG** (VAST-AI) | MIT | **0.393** | 10.6 s (H200) |
| **SAM 3D Objects** (Meta) | SAM License | **0.368** | 8.7 s (H200, fastest measured) |
| **TRELLIS-image-large** (Microsoft) | MIT | **0.347** | 19.4 s (H200) |
| **InstantMesh** (TencentARC) | Apache-2.0 | **0.328** | ~10 s (H200) |
| TripoSR·rembg (local baseline) | MIT | 0.295 | ~15 s (RTX 4050) |
| TripoSR·SAM2 (local baseline) | MIT | 0.278 | ~15 s (RTX 4050) |

Generator ranking: **TripoSG > SAM 3D > TRELLIS > InstantMesh > TripoSR**. The
primary result: **the real catalog mesh (1.000) beats the best generator (0.393) by
~2.5×** — the strongest possible confirmation of the detect→retrieve→parametric
recommendation over generation for BIM
(`deliverable/CLOUD_BENCHMARK_FINDINGS.md`).

**Per-shape complementarity (a real finding).** No single generator dominates
per item. TripoSG/TRELLIS win compact upholstered forms (stool ~0.99) but collapse
on flat planar furniture (table ~0.10); InstantMesh is the opposite — its Zero123++
multiview stage reconstructs the flat table at **0.81** (8× TripoSG) yet trails on
compact pieces; SAM 3D wins the boxy cabinet (**0.73**, best of all generators on
that class) and is top-tier on office_chair (0.63) and stool (0.89) but collapses
on the flat desk (0.05). A *router* — pick the generator by predicted shape class —
would beat any single model. Concrete proof: the best-of-each 10-item IFC4 catalog
built from the study sources its winners from **four different models** (TripoSG
×2, SAM 3D ×4, TRELLIS ×2, InstantMesh ×2)
(`deliverable/CLOUD_BENCHMARK_FINDINGS.md`).

**Further findings from the study** (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`):

- **Finding A — inconsistent mesh orientation.** Generators emit meshes in
  different canonical frames, and even the ABO ground truth is not uniformly
  oriented; fair visual comparison requires per-mesh orientation normalization and
  consistent framing (applied in the project's galleries).
- **Finding B — IFC4-valid but impractically high-poly.** Raw outputs run
  150k–2.7M faces (SAM 3D worst: sofa 1,056,860 faces); a 3-object scene produced a
  138 MB IFC. Decimation to ≤8k faces is mandatory — the best-of-each 10-item IFC4
  catalog is then **2.4 MB** and loads in Revit/ArchiCAD.
- **Finding C — deployment is the real barrier, not the models.** Each model took
  5–9 distinct dependency fixes to produce a single GLB (SAM 3D alone: 12 fixes,
  resolved via its pure-PyTorch `sdpa` attention backend instead of the
  ABI-mismatched `flash_attn` wheel). Licence flag: TRELLIS and InstantMesh depend
  on `nvdiffrast` (NVIDIA Source Code License — research-use OK, commercial flag).
  Full per-model recipes and every error→fix are in `deliverable/manuals/`
  (one manual per model: `TripoSG.md`, `SAM3D.md`, `TRELLIS.md`, `InstantMesh.md`,
  `TRELLIS2.md`; status board and universal gotchas in
  `deliverable/manuals/README.md`).

### 6.2 The in-flight A100 pod run — **results PENDING**

A follow-up cloud run is scripted and documented in
`deliverable/cloud_bundle/RUNBOOK_REMAINING.md`: score the remaining generators on
the **same 10 images, ground truths, scorer, and seed** as the H200 study, and test
the app's own repair + IFC pipeline against each model's output
(`app_pipeline_test.py`). Scope:

- **TRELLIS.2-4B** (separate repo/package from TRELLIS v1; manual pre-written)
- **Stable Fast 3D** (benchmark-only under its licence cap; raw vs cutout A/B)
- **SAM 3D re-run** and **TripoSG re-verify**

Target hardware: RunPod A100 80 GB (preferred) or RTX A6000 48 GB, ~4 h ≈ $3–8
(`RUNBOOK_REMAINING.md`). Integration plan on completion: drop the new meshes into
the benchmark visualizer as extra candidates, update the Research-tab table, and
flip `docs/HUGGINGFACE_MODEL_NARROWING.md` Stage 5 entries to "tested"
(`RUNBOOK_REMAINING.md` §7).

**Results: PENDING — filled in after the 2026-07-11 A100 run.** This section will
be updated with the new score table, per-item winners, and any change to the
router recommendation.

---

## 7. Licensing and Compliance Posture

The posture is **commercial-safe only**: permissive MIT/Apache/BSD (or equivalent
grants), no non-commercial clauses, no revenue caps on adopted components, no MAU
caps, no geographic exclusions, no AGPL-class copyleft in shipped code
(`docs/FINDINGS.md` "Licence posture", `MODEL_SURVEY_SCS.md` §4). A key principle:
SCS sells *outputs* (IFC files and configured rooms), not model weights — so
licences that bind only redistribution of the model have no effect on what SCS
ships; the dangerous licences are those that bind outputs or impose revenue/user
caps (`MODEL_SURVEY_SCS.md` §4).

**Adopted components and their licences** (sources: `README.md` "Licenses",
`docs/FINDINGS.md`, `MODEL_SURVEY_SCS.md`):

| Component | Role | Licence |
|---|---|---|
| TripoSR (Stability AI) | local generative fallback | MIT |
| DINOv2-Large (Meta) | retrieval embedding | Apache-2.0 |
| SAM 2.1 (Meta) | segmentation | Apache-2.0 |
| rembg (U²-Net) | segmentation fallback | MIT |
| Depth Anything V2 **Small** | metric scale | Apache-2.0 (Base/Large are CC-BY-NC — do not upgrade) |
| DETR ResNet-50 (Meta) | detection | Apache-2.0 |
| SAM 3D Objects (Meta) | cloud-class generative candidate | SAM License (royalty-free, no MAU/revenue cap, no geo exclusion; verbatim analysis in `TECHNICAL_REPORT_SCS.md` §6.4) |
| TRELLIS-image-large (Microsoft) | benchmark candidate | MIT (but depends on `nvdiffrast`, NVIDIA Source Code License — commercial flag, `CLOUD_BENCHMARK_FINDINGS.md`) |
| InstantMesh (TencentARC) | benchmark candidate | Apache-2.0 (same `nvdiffrast` flag) |
| TripoSG (VAST-AI) | benchmark winner / router candidate | MIT |
| Amazon Berkeley Objects | retrieval catalog | CC-BY-4.0 (attribution required in product documentation, `MODEL_SURVEY_SCS.md` §9) |
| OR-Tools (Google) | CP-SAT layout solver | Apache-2.0 |
| IfcOpenShell | IFC4 writer | LGPL-3.0 |
| trimesh, pymeshfix, FAISS, PyTorch | geometry / retrieval / DL runtime | MIT / BSD-family (`README.md`, `docs/FINDINGS.md`) |
| xeokit SDK | web viewer | **See note below** |

**Rejected on licence grounds:** Hunyuan3D-2 (EU/UK/S-Korea exclusion + 1M-MAU cap
+ output binding), Stable Fast 3D (US$1M revenue cap — benchmark-only), Wonder3D
(CC-BY-NC), Depth Anything V2 Base/Large (CC-BY-NC), YOLOv8/Ultralytics (AGPL-3.0),
OpenAI CLIP as a deployed model (card disclaimer), Apple DepthPro (`apple-amlr`
research-only), Marigold (CC-BY-SA share-alike) (`docs/FINDINGS.md`,
`MODEL_SURVEY_SCS.md` §7, `docs/HUGGINGFACE_MODEL_NARROWING.md`).

**Open compliance items for legal sign-off:**

1. **xeokit SDK licence discrepancy.** The root `README.md` licence table lists
   xeokit as "AGPL-3.0 / Commercial" and notes a commercial licence is required for
   closed-source deployment, while `docs/FINDINGS.md` and `MODEL_SURVEY_SCS.md` §8
   list xeokit-sdk as MIT. This must be resolved against the installed SDK version
   before commercial distribution.
2. **`nvdiffrast`** (NVIDIA Source Code License) is a dependency of TRELLIS and
   InstantMesh — acceptable for the benchmark, flagged for any production adoption
   of those models (`deliverable/CLOUD_BENCHMARK_FINDINGS.md` Finding C).
3. **ABO attribution** (CC-BY-4.0) must appear in product documentation
   (`MODEL_SURVEY_SCS.md` §9).
4. The AGPL YOLOv8 weights file flagged by the 2026-06-06 audit
   (`MODEL_SURVEY_SCS.md` §9) is no longer present in the repository tree
   (verified absent in this draft); stale references remain in the root
   `README.md` project-structure listing and should be cleaned up.

---

## 8. Deployment Path

### 8.1 Desktop packaging (three stages)

The productization track is staged as follows (packaging work is tracked in the
separate SCS desktop-app repository; this repository contains the application
itself — no in-repo document describes the stages, so they are recorded here as
the agreed plan):

- **Stage A — GitHub Release zip.** Ship the current app as a versioned release
  archive: `npm install` + pinned-Python environment + `npm start`, matching the
  install procedure documented in `README.md` ("Installation", model-weight cache
  table, `.env` configuration).
- **Stage B — Electron + Inno Setup `.exe`.** Wrap the Node server and frontend in
  an Electron shell and produce a Windows installer with Inno Setup, so
  non-technical users get a double-click install.
- **Stage C — code signing.** Sign the installer/executable so Windows SmartScreen
  and enterprise policies accept it.

### 8.2 Runtime modes and hosting

Two deployment modes are documented from measurement
(`docs/WORK_LOG_2026-07-06.md` "Hardware / deployment findings"):

- **Local mode** — needs an NVIDIA GPU with ≥6 GB VRAM (a gaming laptop suffices)
  for photo→3D generation; everything else is light CPU/WebGL.
- **Hosted mode** — GPU on the server; any laptop with a browser works as a
  client.

The server-side hosting pick is the **Hetzner GEX44** dedicated GPU server
(RTX 4000 Ada, 20 GB VRAM): **€184/month + ~€79 setup**, the cheapest German
data-centre option, electricity included, GDPR-clean (`docs/COST_MODEL.md`;
summarized as ~€185/mo with €0 licence royalties in `docs/FINDINGS.md`). The cost
model scales linearly: ~100,000 rooms/month ≈ €1,500/month (≈8× GEX44), comparable
to an on-prem Heilbronn build-out at ~€1,400 (`docs/COST_MODEL.md`). The GPU queue
and per-process VRAM release (§3.2) are what make a single modest GPU serve
iterative multi-user generation safely
(`docs/PART2_ERGONOMICS_AND_ONE_APP_PLAN.md`, `backend/services/gpuQueue.js`).

---

## 9. Current Status and Roadmap

### 9.1 Done (shipped and verified in this repository)

- **One app on :3000; Flask :8000 retired** — generator, room builder, building
  populate, 2D plan editor, demo run (`README.md`).
- **Photo → 3D → IFC pipeline** with SAM2→rembg segmentation, TripoSR generation,
  GPU queue, image-hash cache, auto-registration of generated objects into the room
  catalog (`backend/routes/apiRoutes.js`, `backend/services/gpuQueue.js`,
  `backend/python-scripts/run_triposr.py`).
- **Retrieval engine** ("Fast — from catalog"): DETR → Depth Anything V2 Small →
  DINOv2+FAISS over the ABO catalog, TripoSR fallback, threshold-gated
  (`backend/python-scripts/run_detect_and_place.py`, `docs/CODEBASE_MAP.md`).
- **People-aware room layout** (CP-SAT + rule packs) with honest per-item
  "not enough space", 2D floor-plan fine-tuning with live 3D sync, CSV/GLB/IFC
  export (`README.md`).
- **Building registry + population**: any-IFC upload (sniff/probe/register/
  prepare, cached), per-room suggestions, obstacle-aware furnishing; Duplex
  verified 8 rooms / 0 clashes; four-building fleet demo
  (`backend/routes/buildingRoutes.js`,
  `backend/python-scripts/populate_building.py`, `frontend/fleet.html`).
- **IFC exporter + optimizer**: real IFC4 with `IfcTriangulatedFaceSet` geometry,
  instancing, precision rounding, zip (`backend/python-scripts/saveIFC.py`,
  `optimize_ifc.py`).
- **Repair packs implemented and proven** on the 170-item benchmark with a
  browsable proof gallery (`backend/python-scripts/repair_packs.py`,
  `benchmark/README.md`).
- **5-AI cloud benchmark complete** with per-model reproduction manuals and
  galleries wired into the app's Research hub
  (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`, `deliverable/manuals/README.md`,
  `frontend/hub.html`).
- **System test report** (2026-07-09): six live test campaigns — ingestion sweep,
  concurrency, BIM round-trip, malformed-IFC fuzzing, soak, standards validation
  (`frontend/testing.html`, linked from `frontend/hub.html`).

### 9.2 Pending

- **Repair-pack integration into the default generation path.** The layer is
  implemented with a kill-switch (`SCS_REPAIR_PACKS=0`) and proven standalone
  ("without changing the app", `benchmark/README.md`), but the generation pipeline
  does not yet invoke it by default (no caller outside `repair_packs.py` in
  `backend/` at this draft); merge is awaiting review. Known v3 candidates from the
  benchmark: gentle auto-level for tilted items, sofa blockiness
  (`benchmark/README.md`).
- **Engine selector expansion.** The UI currently offers two engines — "Detailed"
  (TripoSR) and "Fast — from catalog" (`frontend/index.html`). The benchmark's
  complementarity finding argues for exposing additional generators and ultimately
  a shape-class **router** (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`); the heavier
  models are cloud/GEX44-class, not 6 GB-laptop-class (`docs/CODEBASE_MAP.md`
  "Durable project facts").
- **Manuals tab.** The per-model deployment manuals exist as Markdown
  (`deliverable/manuals/`) but are not yet surfaced as a tab inside the app
  alongside the Research hub.
- **Pod-run results integration** — **PENDING — filled in after the 2026-07-11
  A100 run**: score TRELLIS.2-4B / Stable Fast 3D / SAM 3D re-run / TripoSG
  re-verify, feed meshes into the benchmark visualizer, update the Research-tab
  table, and flip `docs/HUGGINGFACE_MODEL_NARROWING.md` Stage 5 to "tested"
  (`deliverable/cloud_bundle/RUNBOOK_REMAINING.md`).
- **Catalog recall speed.** "Fast — from catalog" measured at 22 s per request
  after the threshold fix (down from 53 s); the remaining cost is per-request model
  loading — a warm-model worker targeting ~3–5 s is the next optimization
  (`docs/WORK_LOG_2026-07-06.md`).
- **Compliance close-out**: xeokit licence resolution and ABO attribution in
  product docs (§7 above).
- **Packaging Stages A→C** and hosted-mode deployment on the GEX44 (§8).

---

## 10. Appendix — Glossary of Terms

Plain-language definitions; technical anchors cite where the concept is used.

- **ABO (Amazon Berkeley Objects)** — a public dataset of 7,953 artist-authored 3D
  product meshes (CC-BY-4.0) used as the retrieval catalog and as benchmark ground
  truth (`TECHNICAL_REPORT_SCS.md` §4.6, `docs/ACCURACY_RESULTS.md`).
- **Archetype (repair)** — one of 7 shape families (legged, swivel_seat, boxy,
  upholstered, panel, slender, prop) that selects which repair stages run and how
  aggressively (`backend/python-scripts/repair_packs.py`).
- **BIM (Building Information Modeling)** — the practice of describing buildings
  and their contents as structured, typed data rather than plain drawings.
- **Chamfer distance** — a shape-accuracy metric: the average distance from points
  on one mesh's surface to the nearest point on the other, in both directions.
  Lower is better (`docs/ACCURACY_RESULTS.md`).
- **CLIP** — a neural network that scores how well an image matches a text label;
  used here for object classification and for screening benchmark photos
  (`TECHNICAL_REPORT_SCS.md` §4.5, `benchmark/README.md`).
- **CP-SAT** — Google OR-Tools' constraint-programming solver; here it places
  furniture on a 10 cm grid subject to no-overlap, clearance, and wall-affinity
  constraints (`backend/python-scripts/spatial_layout.py`).
- **Decimation** — reducing a mesh's triangle count while preserving shape (quadric
  method here); mandatory before IFC embedding (`CLOUD_BENCHMARK_FINDINGS.md`
  Finding B).
- **DINOv2** — a self-supervised vision model whose image embeddings capture visual
  structure rather than category language; the retrieval engine's matcher
  (`MODEL_SURVEY_SCS.md` §6.1).
- **F-score@0.02 (F@0.02)** — the harmonic mean of precision and recall of surface
  points that lie within 2% of the object's size of the other surface, after
  alignment. 1.0 = identical shape; the benchmark's headline metric
  (`docs/ACCURACY_RESULTS.md`).
- **FAISS** — Facebook AI Similarity Search; the nearest-neighbour index used for
  catalog retrieval (`docs/FINDINGS.md`).
- **GLB** — the binary form of glTF, the standard web 3D mesh format; the
  pipeline's intermediate format between generation and IFC export.
- **ICP (Iterative Closest Point)** — an algorithm that rigidly aligns two 3D
  shapes; run from multiple seed rotations before scoring so a mesh isn't penalized
  for coming out in a different orientation (`docs/ACCURACY_RESULTS.md`).
- **IFC (Industry Foundation Classes)** — the open, vendor-neutral BIM file
  standard (IFC4 used here). Furniture is written as typed entities (`IfcChair`,
  `IfcDesk`, …) with real triangulated geometry (`backend/python-scripts/saveIFC.py`).
- **IfcTriangulatedFaceSet** — the IFC4 representation for arbitrary triangle
  meshes; how generated geometry is embedded in the IFC file (`saveIFC.py`).
- **IoU (Intersection over Union), silhouette** — overlap between the mesh's
  rendered outline and the photo's object outline; used to prove repairs preserve
  the photographed shape (0.662 → 0.646, `benchmark/README.md`).
- **Marching cubes** — the algorithm that converts a neural network's volumetric
  occupancy field into a triangle mesh (256³ resolution on GPU here,
  `README.md` "How it works").
- **PBR (Physically-Based Rendering)** — the standard material model (base colour,
  roughness, metalness). xeokit requires colour as a PBR `baseColorFactor`
  (`README.md` "Known issues").
- **Plinth** — a solid base slab; rebuilt under boxy/upholstered furniture whose
  generated underside is broken (`repair_packs.py`).
- **rembg / U²-Net** — a background-removal network; the segmentation fallback
  behind SAM2 (`run_triposr.py`).
- **Retrieval-first** — the architecture that matches a photo to an existing
  catalog mesh instead of generating a new one, falling back to generation only
  when no match clears the similarity threshold (§2.3).
- **SAM 2.1 / SAM 3D Objects** — Meta's Segment Anything family: SAM 2.1 produces
  pixel-accurate object masks; SAM 3D Objects reconstructs a posed, textured 3D
  mesh from one image (`MODEL_SURVEY_SCS.md` §6.3, §6.6).
- **Taubin smoothing** — a volume-preserving mesh-smoothing method (unlike plain
  Laplacian smoothing, it does not shrink the object) (`docs/CODEBASE_MAP.md`).
- **TripoSR** — Stability AI's MIT-licensed single-image 3D reconstruction network
  (transformer → triplane field → marching cubes); the local generative fallback
  (`MODEL_SURVEY_SCS.md` §6.10).
- **VRAM** — GPU memory. The 6 GB budget of the dev laptop drives the
  one-job-at-a-time GPU queue and the subprocess-per-generation design
  (`backend/services/gpuQueue.js`).
- **Watertight** — a mesh that encloses volume with no holes or open edges; a
  practical requirement for valid, printable/analyzable BIM geometry
  (`benchmark/README.md`).
- **xeokit / XKT** — the WebGL BIM viewer SDK used for the app's 3D viewport, and
  its compressed binary scene format (`README.md`, `TEAM_ROADMAP.md` §2).

---

*End of document. This report will be finalized — pod-run results inserted in §6.2
and §9.2, packaging stages confirmed in §8.1, and the xeokit licence question
closed in §7 — once the application is declared deployment-ready.*
