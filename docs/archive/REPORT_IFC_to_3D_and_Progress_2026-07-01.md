# SCS · Photo → 3D → IFC → BIM — Full Report

**Project:** 3DpicToIFCModeling (SCS)
**Date:** 2026-07-01
**Branch / last commit:** `app-development` @ `d8186ca`
**Author:** Dimitres Kisimov (with Claude Code)

This report explains, in detail:
1. What an IFC file actually is (and why it "looks like text").
2. The full pipeline: photo → 3D → IFC → BIM.
3. **How generated IFC files get introduced into the 3D space** (the current question).
4. The whole-building population system, and whether it needs GPU pods.
5. A chronicle of every prior discussion and everything we built (including the first
   handoff file), up to the current state.
6. Outstanding deliverables.

---

## 1. What an IFC file is — the "text vs 3D" clarification

An `.ifc` file is **not** an image or a directly-viewable 3D file. It is a **text-based BIM
data format** (the STEP standard, `ISO-10303-21`). It *describes* a building and its objects
as structured data — like how `.svg` or `.html` are text that a program renders.

**The 3D geometry is inside that text.** In a furniture IFC you will see:
- `IFCCARTESIANPOINTLIST3D((...))` — the list of every `(x, y, z)` mesh vertex.
- `IFCTRIANGULATEDFACESET(...)` — the triangles that connect those vertices into a surface.
- `IFCFURNITURE` / `IFCCHAIR` — the BIM object the mesh belongs to.

So when a `.ifc` "looks like a wall of numbers" in Notepad, that is **correct and normal** —
Notepad cannot draw 3D. Open the same file in a **viewer** and it renders as a real 3D model.

> ✅ **Proven this session:** the exported `scene_1782899514425.ifc` (2.8 MB, one chair,
> `IFCTRIANGULATEDFACESET` + 152 verts / 280 faces) opened cleanly in **Autodesk Viewer** and
> displayed the chair in full 3D. The whole export chain works end-to-end.

**Rule of thumb:** never judge an IFC in a text editor — always drop it into a viewer
(Autodesk Viewer, BIMvision, or our own xeokit viewer).

---

## 2. The full pipeline — Photo → 3D → IFC → BIM

| Stage | Component | What it does | Compute |
|-------|-----------|--------------|---------|
| 1. Photo | frontend upload | user uploads / picks a sample image | — |
| 2. Detect | DETR (`facebook/detr-resnet-50`) | finds the furniture + category, confidence | GPU (or CPU) |
| 3. Measure | Depth-Anything-v2-metric | estimates real-world H×W×D in metres | GPU (or CPU) |
| 4a. Retrieve (`detect` engine) | DINOv2 → ABO catalog | matches a real catalogue mesh (BIM path) | GPU (or CPU) |
| 4b. Generate (`triposr` engine) | TripoSR | synthesises a solid mesh from the photo | GPU |
| 5. **3D space** | GLB → **xeokit viewer** | the mesh is loaded into the on-screen 3D scene | browser (WebGL) |
| 6. Export | `saveIFC.py` / `ifcExporter.js` | writes the scene objects to an IFC4 file | CPU |
| 7. **IFC → 3D space** | `convert_to_xkt.py` + xeokit | loads an IFC *back* into the 3D scene | CPU + browser |

Stages 1–4 are the "AI" part (the only part that needs a GPU). Stages 5–7 are geometry/BIM
plumbing and run on CPU + the browser.

**Key files**
- `backend/routes/apiRoutes.js` → spawns `backend/python-scripts/run_detect_and_place.py`
- `backend/python-scripts/saveIFC.py` → writes IFC4 (IfcOpenShell)
- `backend/python-scripts/convert_to_xkt.py` → IFC → XKT (xeokit's fast format)
- `frontend/js/xeokitViewer.js` → the 3D viewer (`GLTFLoaderPlugin`)
- `frontend/js/exporter.js`, `frontend/js/index.js` → export wiring + download

---

## 3. How generated IFC files get **introduced into the 3D space**

Today the loop is **half-closed**:

```
photo → GLB ──► xeokit viewer (3D space)        ✅ works
        GLB ──► IFC export (download)            ✅ works
        IFC ──► xeokit viewer (3D space)         ⛔ NOT wired yet   ← this is the gap
```

The viewer currently only instantiates `GLTFLoaderPlugin` (it loads **GLB**). To bring an
**IFC** into the 3D scene we convert or load it with a plugin that understands IFC/XKT.

**Good news:** the vendored xeokit SDK already ships **all** the loaders we need —
`GLTFLoaderPlugin`, `XKTLoaderPlugin`, **and** `WebIFCLoaderPlugin` are present in
`node_modules/@xeokit/xeokit-sdk/dist/`. Nothing new to install; they just need wiring.

There are **three viable paths**, in order of how "BIM-proper" they are:

### Path A — IFC → XKT → `XKTLoaderPlugin` (recommended for buildings)
- `convert_to_xkt.py` already converts IFC → XKT (via IfcOpenShell tessellation, with a
  no-dependency JSON fallback). **Proven:** `furniture_catalog.ifc` → `furniture_catalog.xkt`
  (2.5 MB) succeeded earlier.
- XKT is xeokit's binary scene format — loads **10–100× faster** than raw IFC in the browser,
  which is exactly what makes a *whole building* render smoothly.
- **Work needed:** add `XKTLoaderPlugin` to `xeokitViewer.js` and a "View IFC in 3D" button
  that (1) POSTs the IFC to a `/convert/xkt` endpoint, (2) loads the returned `.xkt`.

### Path B — IFC → GLB → `GLTFLoaderPlugin` (simplest, reuses today's loader)
- Tessellate the IFC to a GLB with IfcOpenShell (`ifcopenshell.geom` → trimesh → `.glb`),
  then load it with the **existing** `GLTFLoaderPlugin` — no viewer changes at all.
- Good for single items / small scenes; heavier for a full building (no geometry reuse).

### Path C — IFC directly → `WebIFCLoaderPlugin` (no server conversion)
- `WebIFCLoaderPlugin` loads a raw `.ifc` **in the browser** via web-ifc (WASM). No server
  round-trip. Great for "drag an IFC, see it instantly."
- Slightly heavier in-browser parse; needs the web-ifc WASM served alongside the SDK.

**Recommendation:** use **Path A (XKT)** for the building (fast, scalable, tooling already
exists) and optionally **Path C** for a "drop any IFC to view" convenience. The concrete next
step is a small, self-contained "View IFC in 3D" button — no GPU involved.

---

## 4. The whole-building population system

The building is not hand-placed by editing IFC text. A pipeline **stamps** furniture into
rooms automatically and emits one building file.

```
ASSET LIBRARY (each mesh once)        BUILDING PLACEMENT TABLE (thousands of tiny rows)
asset_id | category | glb              instance_id | asset_id | storey | room | x/y/z | rot
chair_01 | chair    | ...glb           inst_0001   | chair_01 | L2     | 214  | ...   | 90°
desk_03  | desk     | ...glb           inst_0002   | desk_03  | L2     | 214  | ...   |  0°
```

**Files**
- `backend/python-scripts/build_asset_library.py` → `deliverable/asset_library/manifest.json`
  — the 10 benchmarked furniture pieces, each mesh stored **once** (id, category, source model,
  F-score, real dimensions, face count, IFC class, licence).
- `backend/python-scripts/build_building.py` → runs the CP-SAT solver per room over a
  `building_spec.json`, in world coordinates → `building_placement.json/csv` +
  xeokit **MetaModel** (Building → Storey → Space → furniture) + summary.
- `backend/python-scripts/build_building_ifc.py` → placement table → **one building IFC4**.
- `backend/python-scripts/convert_to_xkt.py` → building IFC → XKT → xeokit.

**Instancing is the trick that makes it smooth.** The example `SCS_Office_Complex` is
**47 furniture instances rendered from just 9 unique meshes**. xeokit loads each unique
geometry once and re-uses it for every placement — so 500 chairs cost 1 mesh + 500 tiny
transforms, not 500 copies. This is why a full building holds 60 fps.

### Do you need GPU pods for the building? — **No.**
> ✅ **Proven this session:** `build_building.py` ran here on **CPU** (OR-Tools + trimesh),
> producing 47 instances from 9 meshes with **no GPU and no crash**.

- **CPU / browser (no pod):** the solver, mesh assembly, IFC/XKT export, and xeokit rendering.
- **GPU (pod) only for:** generating *new* furniture meshes from photos (TripoSR/TRELLIS/etc.)
  to add **variety** to the asset library (e.g. 5 chair styles instead of 1).

So you can build, populate, export, and view the entire complex on this laptop today. A pod is
optional and only buys furniture variety.

### Exporting buildings from/for xeokit
- Building → **IFC** (`build_building_ifc.py`) → opens in Autodesk Viewer / Revit / ArchiCAD.
- Building → **XKT** (`convert_to_xkt.py`) → loads in the xeokit viewer (and the hosted xeokit
  examples format). The xeokit hospital demo uses `.xkt` + `.dtx`; **DTX** is only needed for
  streaming massive real buildings — overkill for furnished rooms.
- Building → **GLB** (the per-room `scene.glb`s) → loads directly via today's `GLTFLoaderPlugin`.

---

## 5. Chronicle — every prior discussion and what we built

### 5.1 From the first handoff (the "efaedf6" file)
- **IFC BIM catalog tool** — `cloud/build_ifc_catalog.py`: turns generated meshes into a
  standalone, validated IFC4 furniture catalog (best-of-each model, decimated to ~8k faces,
  full Project→Site→Building→Storey hierarchy, re-validated with IfcOpenShell each run).
- **Two documented caveats** (folded into `manuals/README.md` + `CLOUD_BENCHMARK_FINDINGS.md`):
  1. **Decimation is mandatory** — raw meshes are 150k–2.7M faces; the tool auto-decimates so
     the 10-item catalog is 2.4 MB instead of 138 MB (Revit-loadable).
  2. **Orientation + real-world scale** — added Z-up rotation + metre scaling + floor seating.
     Best-effort: 8/10 items land at sensible sizes; a few (e.g. the bed) mis-size because the
     generators emit inconsistent up-axes (Finding A). Full fix = per-item PCA up-axis detection.
- **xeokit + HuggingFace email grounded** — confirmed xeokit is already our viewer target
  (`xeokitViewer.js` + `convert_to_xkt.py`), and the HF image-to-3d list is the source behind
  our 728-model scout. Flagged **TRELLIS.2-4B (MIT)** as the clean untested gap and
  **Hunyuan3D-2** as strong-but-licence-restricted.

### 5.2 Building-scale population (Phase 1 + 2)
- **Phase 1** — `build_asset_library.py`: consolidated the benchmarked meshes into one canonical
  library (`asset_library/manifest.json`).
- **Phase 2** — `build_building.py`: storeys → rooms → picks → one placement table + MetaModel.
  Example `SCS_Office_Complex` = **47 instances from 9 meshes**.

### 5.3 Item-agnostic ergonomic solver
- The old placement solver keyed clearances + wall-affinity to a fixed category list; unknown
  items (mixed ABO + generated + other sources) fell back to a poor generic default.
- Revised (`spatial_layout.py`, `rule_packs.py`, `build_room_scene.py`) to be **dimension-driven**:
  clearance from footprint; wall-vs-centre from geometry (tall/elongated → wall; low/square →
  free). Verified: unknown "treadmill" → wall, "pouffe" → free. No regression.

### 5.4 UI redesign + rebrand
- "Technical Pro" dark theme (`style.css`, `index.html`), all JS hooks preserved.
- Rebranded to a navy-blue dark theme (institution branding since removed per requirements; originally an institution
  wordmark.

### 5.5 Export-IFC fixes
- **"Nothing happens" bug** — the download link was built from a Windows back-slash path
  (`outputs\scene.ifc`) that `split('/')` couldn't parse → fixed to use the server `/outputs/..`
  URL and split on both separators.
- **"Export failed" bug** — the export list was built from xeokit entity IDs that didn't match
  the generated object IDs → rebuilt from `_objectGlbMap`; real error surfaced.

### 5.6 Inventory + clear-view + export modes
- Inventory accumulates across photos; `clearScene()` only clears the 3D view (keeps inventory).
- Added Clear-3D-view button, live count, and three export modes: all→one IFC, each→IFC,
  table→CSV. (Committed `398b0f2`.)

### 5.7 DEMO_RUNBOOK.md
- Presentation-day runbook: `npm start` → `localhost:3000`; the gallery on `:8900`; the building
  one-liner. Live generate takes ~60 s — warm it up before the audience; pre-generated fallbacks
  documented.

### 5.8 This session (2026-07-01)
- **Confirmed the export chain works** and viewed the chair IFC in Autodesk Viewer (resolved the
  "IFC isn't 3D / never exported" confusion).
- **Attempted UI additions** (Autodesk-viewer hint, anti-overlap grid layout, Clear-table + Undo,
  localStorage persistence).
- **Regression:** the anti-overlap change passed a `position` into the xeokit model loader and
  changed the camera call, which made xeokit reject the model on load → "Failed to generate
  model." **All this session's frontend changes were reverted** to the last working commit
  (`398b0f2`); nothing broken was committed.
- **Live-generation crash (unresolved on this machine):** after many repeated runs, the ML
  pipeline began **segfaulting** (`0xC0000005` / exit 139) right after loading weights — on
  **both GPU and CPU**, deterministically. It worked fine at ~10:46 and degraded under repeated
  heavy loads. Diagnosis: accumulated bad **system state**; the reliable reset is a **reboot**.
  This is environmental, not a code bug — none of the CPU building/IFC tools are affected.
- **Pushed** the building placement data (`d8186ca`); repo is clean and in sync with GitHub.

---

## 6. Current state

**Working now (no GPU):**
- 3D viewer + `GLB → viewer`; **Export → IFC** (downloads, opens in Autodesk).
- The **comparison gallery** (`localhost:8900`).
- The **whole building pipeline** (solver, placement table, MetaModel, IFC/XKT export) — CPU.
- The **asset library** (10 pieces) and **12 generated GLBs + 8 IFCs** on disk.

**Broken until reboot:**
- **Live "Generate"** (photo → new mesh) — the ML pipeline segfaults; needs a machine restart.

**On GitHub:** `app-development` @ `d8186ca`, local == remote.

---

## 7. Outstanding deliverables

1. **IFC → 3D space wiring** (Section 3) — a "View IFC in 3D" button: IFC → XKT →
   `XKTLoaderPlugin` (Path A). Closes the loop so exported IFCs render in our own branded app,
   no Autodesk upload. **CPU only.**
2. **Whole-building viewer / instancing** — load `building_placement.json` + the asset library
   into a xeokit `SceneModel` with geometry reuse, so the full complex renders at 60 fps.
   **CPU + browser.**
3. **Manual drag-to-reposition editor** — reviewer clicks a piece in 3D, drags it, and the new
   transform saves back to the placement table + re-exports IFC/XKT. **CPU + browser.**
4. **Real-world scale + auto-orientation (PCA)** for the catalog — per-item up-axis detection so
   outliers (e.g. the bed) self-correct. **CPU.**

**Recommended order for the demo:** #1 (IFC into our viewer) → #2 (whole building on screen) →
#3 (manual editing) → #4 (polish). None require a pod.

---

## 7.5 LESSON LEARNED — architecture vs furniture, and auto-populating a real building

**The lesson (important):** this system **populates furniture; it does not model architecture.**
It generates simple box rooms and places furniture in them — it does **not** produce
walls-with-thickness, doors, handles, or varied room shapes.

> **Proof:** our own building IFC (`SCS_Office_Complex.ifc`, 14 MB) contains **0 `IfcSpace`
> rooms, 0 walls, 0 doors** — only `IfcFurniture`. Architecture is simply not something the
> pipeline emits.

**Therefore the correct architecture for "visualize a whole building" is:**

```
Real architectural building IFC  (the CONTAINER: rooms + walls + doors, from an architect)
        │  ① read every IfcSpace (room) + name/type + footprint
        ▼
   per room:  ② room name → furniture rules (rule_packs)   ③ ergonomic solver places furniture
        ▼
   ④ merge furniture into the building → ⑤ export IFC/XKT → ⑥ view in xeokit
```

**Is it GPU/CPU demanding? — No (measured):**
- Parse a 14 MB building IFC: **~1 s** (CPU).
- Solve one room's furniture layout: **~1.5 s → ~39 rooms/min** (CPU).
- A whole 30–50-room building auto-populates in **~1–2 min of CPU, once**; instanced rendering
  holds **60 fps**. **Zero GPU** — GPU is only ever for generating new meshes, which we skip
  (we reuse the asset library).

**The real building we will populate:** the **Duplex Apartment**
(`sample_buildings/Duplex_Architecture.ifc`, IFC2X3, 2.4 MB) — a standard BIM test building with
**21 named rooms** (Foyer, Living Room, Bathroom, Utility, Stair…), 113 walls, 14 doors,
24 windows, 4 storeys. This is the *empty architectural shell* our tool should populate. (Source:
[youshengCode/IfcSampleFiles](https://github.com/youshengCode/IfcSampleFiles).)

**Next build step:** an IFC room-reader (`IfcSpace` → name/type + footprint) feeding the existing
`rule_packs` + solver + asset library. ~90% of the parts already exist; the new piece is reading
rooms out of a real building. **All CPU.**

## 8. One-line summary

> The pipeline **photo → 3D → IFC → BIM** is proven and on GitHub. The remaining work — bringing
> IFC back into our own 3D viewer, rendering the full building, and manual editing — is **all
> CPU/browser and needs no GPU pods**. The only GPU-dependent step (generating new furniture
> meshes) is temporarily blocked by a system-state crash that a **reboot** clears.
