# Team Roadmap — Phase 2
**Project:** 3D Picture to IFC Modeling  
**Date:** 2026-04-29  
**Team:**  
- **Dimi** — Engineering Lead (coding-intensive tasks)  
- **Gulriz** — Research & Organisation Lead (data, testing, standards, documentation)

> This document is the named-team version of `DEVELOPMENT_ROADMAP_PHASE2.md`.  
> All Phase 1 work (TripoSR GPU pipeline, xeokit viewer, IFC export, YOLO segmentation) is complete and untouched.

---

## 1. Top 3 Image-to-3D AI Models — Commercial Use Verified

All sourced from https://huggingface.co/models?pipeline_tag=image-to-3d&sort=trending as of 2026-04-29.

---

### Model 1 — TRELLIS (Microsoft)
**HuggingFace:** `microsoft/TRELLIS-image-large`  
**License:** MIT ✅ Free for all commercial use, no revenue cap  
**Downloads:** 800+ last month | 600+ likes  

**What it does:**  
State-of-the-art single-image to 3D using Structured Latent Diffusion. Instead of directly generating a mesh, it first generates a structured 3D latent (a combination of 3D Gaussians + voxels), then decodes it into a textured mesh. This two-stage approach produces dramatically sharper geometry and textures than TripoSR.

**Output formats:** GLB (textured), Gaussian splat, radiance field  
**GPU requirement:** 16GB VRAM ideal; can run at reduced quality on 8GB  
**Inference time:** ~30–60s on RTX 4050 with memory optimizations  
**Paper:** arXiv 2412.01506  
**GitHub:** https://github.com/Microsoft/TRELLIS  

**Why it beats TripoSR:** TRELLIS generates multi-view consistent geometry through the structured latent step — no single-view ambiguity. Textures are UV-baked, not vertex-colored. Output meshes have clean topology.

**IFC path:** GLB → trimesh → IfcOpenShell (same pipeline already in place)

---

### Model 2 — InstantMesh (TencentARC)
**HuggingFace:** `TencentARC/InstantMesh`  
**License:** Apache 2.0 ✅ Free for all commercial use  
**Downloads:** 14,000+ last month | 334 likes  

**What it does:**  
Two-stage pipeline: (1) Zero123++ multi-view diffusion generates 6 consistent views of the object from the single input photo, (2) a sparse-view reconstruction model (LRM architecture + differentiable iso-surface extraction) turns those 6 views into a mesh. Having 6 views eliminates single-view ambiguity — the model "sees around" the object.

**Output formats:** GLB, OBJ  
**GPU requirement:** 16GB VRAM recommended; 8GB with chunking  
**Inference time:** ~10s on a high-end GPU  
**Paper:** arXiv 2404.07191  
**GitHub:** https://github.com/TencentARC/InstantMesh  

**Why it is relevant:** Already partially scaffolded in this codebase (`run_instantmesh.py`). Replacing the current depth-map placeholder with the real InstantMesh weights is a direct upgrade path.

**IFC path:** GLB → trimesh → IfcOpenShell

---

### Model 3 — Hunyuan3D-2 / 2.1 (Tencent)
**HuggingFace:** `tencent/Hunyuan3D-2` / `tencent/Hunyuan3D-2.1`  
**License:** Hunyuan Community License ✅ free for commercial use under standard terms  
**Downloads:** 74,000+ (v2) | 1,750 likes — highest download count on the list  

**What it does:**  
Two-stage architecture: shape generation + texture generation (PBR materials). Generates production-ready assets with physically-based rendering (roughness, metallic, normal maps). Text-to-3D and Image-to-3D both supported. Version 2.1 adds improved PBR materials.

**Output formats:** GLB with full PBR textures (albedo, roughness, metallic, normal maps)  
**GPU requirement:** 24GB VRAM for full quality; quantized versions available for lower VRAM  
**Inference time:** 2–5 min depending on texture quality  
**GitHub:** https://github.com/Tencent-Hunyuan/Hunyuan3D-2  

**Why it matters:** The PBR texture output is the most production-ready of any open model. For office furniture that needs to look realistic in a BIM viewer, Hunyuan3D-2 produces the best visual output.

**IFC path:** GLB (with PBR materials) → trimesh / GLTF → IfcOpenShell  
**Note:** Verify commercial terms at https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE before deployment.

---

### Honorable mention — Stable Fast 3D (Stability AI)
**HuggingFace:** `stabilityai/stable-fast-3d`  
**License:** Community license — free if annual revenue < $1M USD  
**What it does:** Sub-1-second inference, UV-unwrapped textured mesh. Best speed/quality ratio. Already scaffolded in this codebase (`run_stablefast3d.py`).

---

### IFC Compliance note
None of these models output IFC natively. All output GLB or OBJ. IFC compliance is achieved downstream via IfcOpenShell, which wraps the mesh geometry into an IFC entity (IfcFurnishingElement, IfcBuildingElementProxy, etc.). This is already implemented. The models above all produce geometrically cleaner meshes than TripoSR, making the IFC wrapping more accurate.

---

## 2. Exporting Inventory to a Public xeokit Web Viewer

**Reference target:** https://xeokit.github.io/xeokit-sdk/examples/buildings/#xkt_dtx_HolterTower

The HolterTower example uses **XKT format** — xeokit's compressed binary format loaded via `XKTLoaderPlugin`. XKT is ~10x smaller than IFC and loads in the browser in under 1 second for large buildings.

### Pipeline: IFC → XKT → hosted xeokit viewer

```
Generated GLB
    │
    ▼
IfcOpenShell                → .ifc file (already implemented)
    │
    ▼
@xeokit/xeokit-convert CLI  → .xkt file (binary, compressed)
    │
    ▼
Static web host             → serve .xkt + xeokit viewer HTML
    │
    ▼
XKTLoaderPlugin             → renders in browser like HolterTower
```

### Step-by-step implementation

**Step 1 — Install xeokit-convert**
```bash
npm install -g @xeokit/xeokit-convert
```

**Step 2 — Convert IFC to XKT**
```bash
ifc2xkt -s ./outputs/scene.ifc -o ./outputs/scene.xkt
```

**Step 3 — Standalone viewer HTML** (`viewer/index.html`)
```html
<!DOCTYPE html>
<html>
<head>
  <script type="module" src="/vendor/xeokit-sdk/xeokit-sdk.min.es.js"></script>
</head>
<body>
  <canvas id="xeokit-canvas"></canvas>
  <script type="module">
    import * as xeokit from '/vendor/xeokit-sdk/xeokit-sdk.min.es.js';
    window.xeokit = xeokit;

    const viewer = new xeokit.Viewer({ canvasId: 'xeokit-canvas' });
    const loader = new xeokit.XKTLoaderPlugin(viewer);

    loader.load({
      id: 'office-model',
      src: '/outputs/scene.xkt',
      edges: true
    });
  </script>
</body>
</html>
```

**Step 4 — Add IFC→XKT route to Express backend**
```js
// backend/routes/export.js
app.post('/api/export/xkt', async (req, res) => {
  const { ifcPath } = req.body;
  const xktPath = ifcPath.replace('.ifc', '.xkt');
  await exec(`ifc2xkt -s ${ifcPath} -o ${xktPath}`);
  res.json({ success: true, xktUrl: `/outputs/${path.basename(xktPath)}` });
});
```

**Step 5 — Deploy publicly**  
Any static host works: Netlify, GitHub Pages, Vercel (all free). The `.xkt` file and viewer HTML are the only files needed. No server required for viewing.

---

## 3. AI for Office Spatial Positioning

**Goal:** Given a room outline and a list of detected furniture items (chairs, desks, monitors, printers, cupboards), automatically place them in positions that satisfy office ergonomics and regulatory standards.

### Standards to encode

| Standard | Key rules |
|----------|-----------|
| OSHA 29 CFR 1910 | Min 4.65 m² (50 sq ft) per workstation; aisles ≥ 1.12m |
| ADA Standards | Accessible route ≥ 914mm; one accessible workstation per type |
| ISO 9241-5 | Monitor 50–70cm from eyes; screen top at or below eye level |
| NFPA 101 (Life Safety) | Clear path to exit at all times; no egress obstruction |
| BIFMA G1 | Ergonomic guidelines for office seating and desk heights |

### Recommended AI algorithms (free, open source, commercially usable)

**Option A — ATISS (Autoregressive Transformers for Indoor Scene Synthesis)**
- License: MIT ✅
- GitHub: https://github.com/nv-tlabs/ATISS
- What it does: Given a room polygon, autoregressively places furniture objects one at a time using a transformer trained on real indoor layouts (3D-FRONT dataset)
- Strength: Learned real-world spatial distributions — chairs cluster around desks, printers near walls
- Limitation: Trained on residential scenes; needs fine-tuning on office layouts

**Option B — DiffuScene**
- License: MIT ✅
- GitHub: https://github.com/tangjiapeng/DiffuScene
- What it does: Diffusion model over furniture placements — generates all object positions simultaneously
- Strength: Globally coherent layouts; handles many objects at once

**Option C — Rule-based constraint solver (no training required)**
- Libraries: OR-Tools (Google, Apache 2.0), scipy.optimize, PuLP
- Encodes all standards above as hard constraints and an objective function
- Strength: Deterministic, always compliant, auditable

### Recommended hybrid approach: Rule-based constraints + ATISS refinement

```
Room polygon + furniture list
        │
        ▼
OR-Tools constraint solver
  - Enforce all hard constraints (ADA, OSHA, NFPA)
  - Place items within valid zones
        │
        ▼
ATISS refinement pass
  - Adjust positions within constraint bounds
  - Add natural clustering and spacing
        │
        ▼
Output: list of (object_id, x, y, z, rotation)
        │
        ▼
Apply transforms in xeokit viewer
        │
        ▼
Export to IFC with positioned objects
```

### Training dataset
- **3D-FRONT** — 18,800 professional interior designs including offices. Free for research and commercial use with registration: https://tianchi.aliyun.com/specials/promotion/alibaba-3d-future

---

## 4. Team Structure

### Dimi — Engineering Lead

**Role:** Coding-intensive implementation tasks  

**Responsibilities:**
- Implement new AI model adapters (TRELLIS, real InstantMesh, Hunyuan3D-2)
- Build XKT export pipeline and hosted viewer
- Integrate spatial positioning solver (OR-Tools + ATISS)
- Backend API development and Node.js routes
- Git management, branching strategy, CI

**Daily workflow:**
1. Pull from `main`
2. Create feature branch (`feat/trellis-adapter`, `feat/xkt-export`, etc.)
3. Implement and test locally
4. Open PR with description for Gulriz to review context
5. Merge to `main` after self-review

---

### Gulriz — Research & Organisation Lead

**Role:** Research, data curation, testing, standards documentation  

**Responsibilities:**
- Test each AI model with diverse office furniture photos (chairs, desks, monitors, printers, cupboards)
- Document output quality per model per object type (scoring grid, CSV logs)
- Collect and curate training data for ATISS fine-tuning (3D-FRONT office subset)
- Encode office standards (OSHA, ADA, ISO 9241, NFPA, BIFMA) into constraint specification documents
- Validate IFC exports open correctly in Revit / AutoCAD / BIM viewers
- Write and run end-to-end test scripts comparing pipeline outputs

**Daily workflow:**
1. Pull from `main`
2. Run test image batches through the pipeline using test scripts
3. Log results in `tests/results/` (quality scores, screenshots, timings)
4. File GitHub Issues for failures or quality regressions
5. Update documentation and constraint specs

---

## 5. Free VS Code-Compatible Software Stack

### For both Dimi and Gulriz

| Tool | Type | Why | License |
|------|------|-----|---------|
| **VS Code** | IDE | Primary editor | Free |
| **GitLens** | VS Code ext | Full git history, blame, branches | Free |
| **GitHub Pull Requests** | VS Code ext | Review PRs without leaving VS Code | Free |
| **Prettier** | VS Code ext | Auto-format JS/TS/JSON/Python | Free |
| **ESLint** | VS Code ext | JS linting | Free |
| **Python (Microsoft)** | VS Code ext | IntelliSense, debugging | Free |
| **Pylance** | VS Code ext | Fast Python type checking | Free |
| **Jupyter** | VS Code ext | Run notebooks inside VS Code | Free |
| **Thunder Client** | VS Code ext | REST API testing (Postman alternative) | Free |
| **Docker** | VS Code ext | Container management | Free |

### For Dimi (engineering)

| Tool | Type | Why | License |
|------|------|-----|---------|
| **Continue.dev** | VS Code ext | Free open-source AI coding assistant; works with local Ollama models or Claude API | Apache 2.0 |
| **Codeium** | VS Code ext | Free AI autocomplete, no revenue cap | Free |
| **REST Client** | VS Code ext | Send HTTP requests from `.http` files | MIT |
| **Error Lens** | VS Code ext | Inline error highlighting | MIT |
| **GLSL Lint** | VS Code ext | WebGL shader validation | MIT |
| **Blender** *(separate app)* | 3D editor | Inspect/fix generated meshes; fully Python-scriptable | GPL (free) |

### For Gulriz (research)

| Tool | Type | Why | License |
|------|------|-----|---------|
| **Label Studio** | Web app (local) | Annotate images for segmentation training; launch from VS Code terminal | Apache 2.0 |
| **DVC** | VS Code ext + CLI | Data version control — track model weights and datasets like git | Apache 2.0 |
| **CSV to Table** | VS Code ext | View test result CSVs as formatted tables | MIT |
| **Markdown Preview Mermaid** | VS Code ext | Render diagrams in markdown docs | MIT |
| **Weights & Biases** *(free tier)* | Web dashboard | Track experiment runs, compare model outputs, log metrics | Free tier |
| **Meshlab** *(separate app)* | 3D mesh inspector | Open and inspect GLB/OBJ output quality without code | GPL (free) |

### Collaboration tools

| Tool | Why | Cost |
|------|-----|------|
| **GitHub** | Code, PRs, Issues, Projects board | Free |
| **GitHub Projects** | Kanban board for task tracking between Dimi and Gulriz | Free |
| **GitHub Discussions** | Async Q&A and decisions | Free |
| **Hugging Face Spaces** | Host public demo of the pipeline | Free tier |

---

## 6. Full Implementation Plan — 8 Sprints (~12 weeks)

Builds directly on existing Phase 1 infrastructure. No existing files removed or replaced — additions and extensions only.

---

### Sprint 1 — Real InstantMesh integration (Week 1–2)
**Dimi implements | Gulriz tests**

The current `run_instantmesh.py` uses a depth-map placeholder. Replace with the real model.

- [ ] **Dimi:** Download InstantMesh weights: `TencentARC/InstantMesh` (~5GB)
- [ ] **Dimi:** Rewrite `backend/python-scripts/run_instantmesh.py` to call real Zero123++ + LRM pipeline
- [ ] **Dimi:** Add `zero123plus` and `einops` to requirements
- [ ] **Gulriz:** Test with 10 office objects, document quality vs TripoSR in `tests/results/sprint1_instantmesh.csv`
- [ ] **Dimi:** Merge to `main`

---

### Sprint 2 — TRELLIS integration (Week 2–3)
**Dimi implements | Gulriz stress-tests**

TRELLIS is the highest-quality available model. Needs memory optimisation for the RTX 4050's 6GB VRAM.

- [ ] **Dimi:** Clone TRELLIS into `backend/trellis/`
- [ ] **Dimi:** Install dependencies: `pip install git+https://github.com/Microsoft/TRELLIS`
- [ ] **Dimi:** Create `backend/python-scripts/run_trellis.py` with memory optimisations (`torch.cuda.empty_cache()`, chunked rendering)
- [ ] **Dimi:** Add TRELLIS as fourth option in frontend model selector
- [ ] **Dimi:** Wire `backend/ai/trellis.js` adapter
- [ ] **Gulriz:** Test 20 photos, score quality 1–10, log to `tests/results/sprint2_trellis.csv`

---

### Sprint 3 — XKT export and hosted viewer (Week 3–4)
**Dimi builds pipeline | Gulriz validates in Revit/BIM tools**

- [ ] **Dimi:** Install `npm install -g @xeokit/xeokit-convert`
- [ ] **Dimi:** Add `POST /api/export/xkt` endpoint to `backend/routes/export.js`
- [ ] **Dimi:** Create `viewer/` directory with standalone xeokit XKTLoaderPlugin HTML
- [ ] **Dimi:** Add "Export to XKT" button to frontend beside the existing IFC export button
- [ ] **Gulriz:** Open exported XKT files in hosted viewer, verify geometry matches source photo
- [ ] **Gulriz:** Validate IFC files open in Revit/AutoCAD without import errors
- [ ] **Dimi:** Deploy static viewer to GitHub Pages or Netlify (free)

---

### Sprint 4 — Office object detection and classification (Week 4–5)
**Gulriz curates dataset | Dimi wires the classifier**

Before spatial placement, each detected object needs a category label.

- [ ] **Gulriz:** Collect 200 labelled images of: chairs, desks, monitors, printers, cupboards, tables using Label Studio
- [ ] **Gulriz:** Export annotations in YOLO format
- [ ] **Dimi:** Fine-tune YOLOv8 classification head on these categories (`yolov8n-cls.pt` base)
- [ ] **Dimi:** Update `inference_base.py` to return object category label alongside the mesh
- [ ] **Dimi:** Store category in GLB metadata and pass through to IFC (`IfcChair`, `IfcDesk`, etc.)

---

### Sprint 5 — Spatial positioning engine (Week 5–7)
**Dimi builds solver | Gulriz encodes standards and validates**

- [ ] **Gulriz:** Write `docs/OFFICE_STANDARDS.md` — all OSHA/ADA/ISO 9241/NFPA/BIFMA rules as structured constraint specifications
- [ ] **Dimi:** Install OR-Tools: `pip install ortools`
- [ ] **Dimi:** Create `backend/python-scripts/spatial_solver.py`
  - Input: room polygon (wall vertices), list of objects with categories and dimensions
  - Output: list of (object_id, x, y, z, rotation_y)
  - Hard constraints: aisle widths, egress paths, ADA clearances
  - Soft objective: maximise workstation density, cluster chairs to desks
- [ ] **Dimi:** Add `POST /api/layout/auto` endpoint
- [ ] **Dimi:** Frontend "Auto-arrange" button applies returned transforms in xeokit
- [ ] **Gulriz:** Validate 5 generated layouts against `OFFICE_STANDARDS.md`, file GitHub Issues for any violations

---

### Sprint 6 — ATISS fine-tuning on office layouts (Week 7–9)
**Gulriz prepares data | Dimi trains and integrates**

- [ ] **Gulriz:** Download 3D-FRONT office subset, convert to ATISS training format
- [ ] **Dimi:** Fine-tune ATISS for 50 epochs on office layouts (local RTX 4050 or Google Colab free tier)
- [ ] **Dimi:** Replace rule-only solver with ATISS + constraint validation pass
- [ ] **Gulriz:** Compare 10 ATISS-generated layouts vs 10 rule-solver-only layouts, score and document

---

### Sprint 7 — Hunyuan3D-2 integration (Week 9–10)
**Dimi integrates | Gulriz tests texture quality**

Hunyuan3D-2 produces the best PBR textures. Needs 24GB VRAM ideally — evaluate quantized variant for RTX 4050.

- [ ] **Dimi:** Evaluate whether quantized Hunyuan3D-2 mini runs on 6GB VRAM
- [ ] **Dimi:** If yes — integrate locally; if no — wire HuggingFace Inference API endpoint
- [ ] **Dimi:** Create `backend/python-scripts/run_hunyuan3d.py`
- [ ] **Dimi:** Add Hunyuan3D as model option in frontend
- [ ] **Gulriz:** Document texture quality improvement vs TripoSR in `tests/results/sprint7_hunyuan3d.csv`

---

### Sprint 8 — Polish, testing, public demo (Week 10–12)
**Dimi + Gulriz**

- [ ] **Dimi:** End-to-end integration test — upload photo → AI model → xeokit → IFC → XKT → hosted viewer
- [ ] **Gulriz:** Create test suite with 30 diverse office objects, run all 4 models, compile quality comparison table
- [ ] **Gulriz:** Write user-facing workflow documentation
- [ ] **Dimi:** Containerise with Docker for reproducible setup
- [ ] **Dimi:** Deploy hosted demo to Hugging Face Spaces (free, public pipeline showcase)
- [ ] **Dimi + Gulriz:** Final commit — updated README, full documentation, all test results

---

## 7. New files to be added (nothing existing deleted)

```
3DpicToIFCModeling/
├── backend/
│   ├── trellis/                        ← TRELLIS source (Sprint 2)
│   ├── ai/
│   │   └── trellis.js                  ← TRELLIS adapter (Sprint 2)
│   └── python-scripts/
│       ├── run_trellis.py              ← TRELLIS inference (Sprint 2)
│       ├── run_hunyuan3d.py            ← Hunyuan3D-2 inference (Sprint 7)
│       └── spatial_solver.py          ← OR-Tools layout engine (Sprint 5)
├── viewer/
│   └── index.html                      ← Standalone XKT viewer (Sprint 3)
├── tests/
│   ├── run_all_models.py               ← Batch quality test script
│   └── results/                        ← CSV quality logs (Gulriz)
├── docs/
│   └── OFFICE_STANDARDS.md             ← Constraint specifications (Gulriz)
└── TEAM_ROADMAP.md                     ← THIS FILE
```

---

## 8. Summary table

| Item | Status | Owner | Sprint |
|------|--------|-------|--------|
| Real InstantMesh weights | Planned | Dimi + Gulriz | 1 |
| TRELLIS integration | Planned | Dimi + Gulriz | 2 |
| XKT export + hosted viewer | Planned | Dimi + Gulriz | 3 |
| Object classification (YOLO fine-tune) | Planned | Gulriz + Dimi | 4 |
| Spatial positioning (OR-Tools) | Planned | Dimi + Gulriz | 5 |
| ATISS office fine-tuning | Planned | Gulriz + Dimi | 6 |
| Hunyuan3D-2 integration | Planned | Dimi + Gulriz | 7 |
| Public demo deploy | Planned | Dimi + Gulriz | 8 |
| TripoSR pipeline (GPU, RTX 4050) | ✅ Done | — | Phase 1 |
| xeokit viewer (local, WebGL) | ✅ Done | — | Phase 1 |
| IFC export (IfcOpenShell) | ✅ Done | — | Phase 1 |
| YOLO segmentation (yolov8n-seg) | ✅ Done | — | Phase 1 |
| PBR material color fix | ✅ Done | — | Phase 1 |
| GPU acceleration (CUDA 12.6) | ✅ Done | — | Phase 1 |
