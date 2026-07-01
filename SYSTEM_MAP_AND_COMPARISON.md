# SCS 3DpicToIFC — System Map, Comparison Files & Storage

A few-page guide to: (1) how to **show the RunPod benchmark comparison**, (2) **every Python file** and
what it does, (3) the **data-flow arrows**, and (4) **what is stored where**.

---

## 1. How to SHOW the comparison (RunPod H200 benchmark)

Five single-image→3D generators were run on a **RunPod H200 GPU** and scored per furniture item.
The results live under `deliverable/cloud_gallery/` and `deliverable/cloud_results/`.

**Show the interactive comparison gallery** (5 models spinning side-by-side + scores):
```bash
python deliverable/cloud_gallery/serve.py       # serves on http://localhost:8900/
#   (or double-click deliverable/cloud_gallery/serve.bat on Windows)
```
Then open **http://localhost:8900/** — it reads `cloud_scores.csv` and the per-model meshes.

**Static / offline versions (no server):**
- `deliverable/cloud_gallery/gallery_static.html` — open directly in a browser
- `deliverable/cloud_comparison_montage.png` — one image, all models side-by-side
- `deliverable/cloud_gallery/cloud_scores.csv` — the raw numbers (open in Excel)

**What the comparison shows (F-score, higher = better):**
```
             RunPod H200  →  cloud_results/<model>/<item>.glb  →  scored vs ABO ground truth
                                                                      │
  overall mean F:  TripoSG 0.393 > SAM 3D 0.368 > TRELLIS 0.347 > InstantMesh 0.327 > TripoSR
  best-of-each →   deliverable/asset_library/  (stool 0.99 TripoSG, table 0.81 InstantMesh, …)
```

**Where the benchmark data is stored:**
```
deliverable/
├── cloud_gallery/
│   ├── index.html         ← interactive gallery (served on :8900)
│   ├── serve.py / serve.bat ← launches the gallery server
│   ├── cloud_scores.csv   ← F-score + Chamfer per (item × model)  [61 rows]
│   ├── gallery_static.html← no-server version
│   └── assets/            ← thumbnails / rendered previews
├── cloud_results/         ← the RAW meshes from the pod
│   ├── triposg/  sam3d/  trellis/  instantmesh/   (one .glb per item per model)
│   └── _bim_catalog/      ← decimated IFC4 catalog built from the winners
├── cloud_comparison_montage.png   ← single composite image
├── CLOUD_BENCHMARK_FINDINGS.md    ← written findings
└── asset_library/         ← BEST-of-each mesh per category (used by the building tools)
```

---

## 2. Data-flow (the arrows)

### A. Per-item pipeline (the :3000 generator app)
```
 photo.jpg
    │
    ▼  run_detect_and_place.py
 ┌─────────────────────────────────────────────────────────────┐
 │ DETR detect ─▶ Depth-Anything-v2 (real H×W×D) ─▶ DINOv2       │
 │ retrieve ABO mesh   ── or ──▶  TripoSR generate                │
 └─────────────────────────────────────────────────────────────┘
    │ mesh.glb
    ▼  saveIFC.py
 model.ifc  ──▶  convert_to_xkt.py ──▶ .xkt ──▶ xeokit viewer
             └─▶  ifc_to_glb.py    ──▶ .glb ──▶ xeokit viewer / Autodesk
```

### B. Building population (the :8000 app)
```
 real building IFC (sample_buildings/Duplex_Architecture.ifc)
    │
    ▼  populate_building.py
 ┌──────────────────────────────────────────────────────────────────────┐
 │ read IfcSpace rooms (name+footprint)                                   │
 │      ▼                                                                 │
 │ smart_furnish()  ─ measure type+area → pick a FITTING set              │
 │      ▼   (rule_packs.py = Neufert/Panero/ADA)                          │
 │ extract obstacles (walls/beams/columns/doors) ─▶ merge (shapely)       │
 │      ▼                                                                 │
 │ spatial_layout.py  (CP-SAT solver) ─ place AROUND obstacles, 0 clashes │
 └──────────────────────────────────────────────────────────────────────┘
    │  shell.glb  +  piece_N.glb (each movable)  +  furniture.json
    ▼  app_server.py  (/populate → drag in xeokit → /save)
 building.glb  (download)   ──▶  build_building_ifc.py ──▶ building.ifc
```

### C. Benchmark (how the comparison was produced)
```
 items ──▶ [RunPod H200] run each generator ──▶ cloud_results/<model>/<item>.glb
                                                     │
        eval_accuracy.py / score_abo_test.py ──▶ cloud_scores.csv ──▶ cloud_gallery (:8900)
                                                     │
        build_asset_library.py ──▶ asset_library/  (best-of-each, decimated, real-scale)
```

---

## 3. The Python files (by role)  — `backend/python-scripts/`

### Inference / generators  (run a model → mesh)
| File | Does |
|------|------|
| `run_detect_and_place.py` | THE live pipeline: DETR detect → depth → DINOv2/ABO retrieve → GLB |
| `inference_base.py` | shared helpers (logging, segmented-depth mesh, GLB export) |
| `run_triposr.py` | TripoSR generative reconstruction |
| `run_trellis_wsl.py` | TRELLIS (via WSL2) |
| `run_instantmesh.py` | InstantMesh |
| `run_stablefast3d.py` | StableFast3D placeholder (YOLO+DPT depth mesh) |
| `run_meshy_api.py` | Meshy cloud API |

### IFC / BIM  (mesh → IFC / XKT / GLB)
| File | Does |
|------|------|
| `saveIFC.py` | write a scene of objects to **IFC4** (geometry + hierarchy) |
| `createIFCFurniture.py` | single-furniture IFC helper |
| `build_room_ifc.py` | one room → IFC |
| `build_building_ifc.py` | building placement table → one building IFC |
| `convert_to_xkt.py` | IFC → XKT (xeokit's fast format) |
| `ifc_to_glb.py` | IFC → GLB (skips furniture → empty shell) |

### Layout / catalog / building  (place & assemble)
| File | Does |
|------|------|
| `spatial_layout.py` | **CP-SAT ergonomic solver** — no-overlap, clearances, obstacles |
| `rule_packs.py` | per-room-type standards (Neufert/Panero/ADA), clearances, groups |
| `catalog.py` | user picks + room type → anchored scene spec; picker data |
| `build_room_scene.py` | one room spec → scene.glb + metamodel + schedule |
| `build_asset_library.py` | benchmarked meshes → canonical **asset_library** |
| `build_building.py` | storeys→rooms→picks → building placement table |
| `populate_building.py` | **auto-populate a real IFC** (rooms → smart furnish → solve) |
| `merge_building_glb.py` | merge per-room GLBs → one positioned building GLB |
| `render_scene.py` / `make_scene_spec.py` | server-side render / spec helper |

### Benchmark / evaluation  (score the generators)
| File | Does |
|------|------|
| `eval_accuracy.py`, `eval_bakeoff.py`, `eval_photo3d.py` | scoring harnesses (F-score/Chamfer) |
| `score_abo_test.py`, `batch_abo_test.py` | ABO scoring / batch runs |
| `objaverse_benchmark.py`, `polyhaven_benchmark.py` | extra dataset benchmarks |

### Data / gallery / figures  (build the deliverables)
| File | Does |
|------|------|
| `download_abo_subset.py`, `build_abo_index.py`, `build_mesh_library.py` | build the ABO/mesh libraries + FAISS index |
| `build_abo_gallery.py`, `export_abo_gallery.py`, `make_previews.py` | galleries + thumbnails |
| `make_paper_figures.py`, `make_accuracy_figure.py`, `make_results_plate.py` | paper figures |
| `build_pptx.py`, `build_docx.py`, `build_html_deck.py`, `collect_all.py` | slide deck / doc / bundle |

### Mesh utilities
`cleanMesh.py`, `normalizeMesh.py`, `fixOrientation.py`, `meshToGLB.py`, `render_glb_preview.py`,
`_triposr_postprocess.py`, `_tsr_state_dict_remap.py` (TripoSR weight-load fix).

### Backend apps (not in python-scripts)
- `backend/app_server.py` — **Flask** :8000 (building population + upload). 
- `backend/server.js` + `backend/routes/*.js` — **Node/Express** :3000 (generator app).

---

## 4. What is stored WHERE  (top-level map)

```
3DpicToIFCModeling/
├── backend/
│   ├── server.js, routes/, services/     ← Node app (:3000)
│   ├── app_server.py                     ← Flask app (:8000)
│   └── python-scripts/                   ← ALL 54 python files (see §3)
├── frontend/
│   ├── index.html, js/                   ← the :3000 generator UI
│   └── *_building_viewer.html            ← standalone xeokit building viewers
├── demo/
│   ├── app.html, app.js                  ← the :8000 room/building UI
│   └── app_out/                          ← SCRATCH preview (wiped each run: scene.glb, /bldg, building.glb)
├── data/                                 ← INPUT libraries (source assets)
│   ├── mesh_library_abo/                 ← ~400 Amazon Berkeley Objects meshes + thumbnails (retrieval)
│   ├── mesh_library/, furniture_library/ ← procedural/mesh libraries
│   ├── generated_assets/                 ← 🆕 user-uploaded generated items (+ manifest.json)
│   ├── demo_photos/, office_images/      ← sample input photos
│   └── mesh_library_polyhaven/           ← extra benchmark meshes
├── sample_buildings/
│   └── Duplex_Architecture.ifc           ← the real empty building to populate
├── outputs/                              ← RUNTIME outputs (gitignored): mesh_*.glb, scene_*.ifc, duplex_*.glb
├── deliverable/                          ← FINISHED artifacts
│   ├── cloud_gallery/  cloud_results/    ← the RunPod benchmark (see §1)
│   ├── asset_library/                    ← best-of-each meshes (used by building tools)
│   ├── building/SCS_Office_Complex/      ← example building placement table + metamodel
│   ├── figures/  papers/  manuals/  docs/← paper assets, write-ups
│   ├── PAPER_*.docx/.pptx, PAPER_MASTER.md
│   └── CLOUD_BENCHMARK_FINDINGS.md, all_scores.csv
└── *.md  (root docs)
    ├── ROADMAP.md                        ← status/next/backlog
    ├── FOUNDATION_FOR_RESEARCH_PAPER.md  ← everything for the paper
    ├── README.md, DEMO_RUNBOOK.md, SYSTEM_MAP_AND_COMPARISON.md (this file)
```

**Rule of thumb:** `data/` = inputs · `outputs/` = throwaway runtime files · `deliverable/` = finished
things you show/ship · `sample_buildings/` = the building to furnish · code lives in `backend/` + `demo/` + `frontend/`.

---

## 5. Quick commands
```bash
# Show the RunPod comparison gallery
python deliverable/cloud_gallery/serve.py            # → http://localhost:8900/

# Run the building-population app (pick building → furnish → drag → save; upload-your-own)
python backend/app_server.py                          # → http://localhost:8000/

# Run the photo→3D→IFC generator app
node backend/server.js                                # → http://localhost:3000/

# CLI: auto-populate the Duplex
python backend/python-scripts/populate_building.py sample_buildings/Duplex_Architecture.ifc out.glb
```
