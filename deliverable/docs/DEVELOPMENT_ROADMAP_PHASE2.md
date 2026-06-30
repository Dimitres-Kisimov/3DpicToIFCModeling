# Development Roadmap — Phase 2
**Project:** 3D Picture to IFC Modeling  
**Date:** 2026-04-29  
**Team size:** 2 members  
**Builds on:** All Phase 1 work (TripoSR pipeline, xeokit viewer, IFC export, GPU acceleration)

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

**IFC path:** GLB → trimesh → IfcOpenShell (same pipeline we have now)

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

**Why it is relevant:** Already partially scaffolded in our codebase (`run_instantmesh.py`). Replacing the current depth-map placeholder with the real InstantMesh weights is a direct upgrade path. Outputs mesh immediately, no post-processing depth tricks.

**IFC path:** GLB → trimesh → IfcOpenShell

---

### Model 3 — Hunyuan3D-2 / 2.1 (Tencent)
**HuggingFace:** `tencent/Hunyuan3D-2` / `tencent/Hunyuan3D-2.1`  
**License:** Hunyuan Community License (free for commercial use under standard terms, must review for revenue thresholds)  
**Downloads:** 74,000+ (v2) | 1,750 likes — highest download count on the list  

**What it does:**  
Two-stage architecture: shape generation + texture generation (PBR materials). Generates production-ready assets with physically-based rendering (roughness, metallic, normal maps). Text-to-3D and Image-to-3D both supported. Version 2.1 adds improved PBR materials.

**Output formats:** GLB with full PBR textures (albedo, roughness, metallic, normal maps)  
**GPU requirement:** 24GB VRAM for full quality; quantized versions available  
**Inference time:** 2–5 min depending on texture quality  
**GitHub:** https://github.com/Tencent-Hunyuan/Hunyuan3D-2  

**Why it matters:** The PBR texture output is the most production-ready of any open model. For office furniture that needs to look realistic in a BIM viewer, Hunyuan3D-2 produces the best visual output.

**IFC path:** GLB (with PBR materials) → trimesh / GLTF → IfcOpenShell  
**Note:** Verify commercial terms at https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE before deployment.

---

### Honorable mention — Stable Fast 3D (Stability AI)
**HuggingFace:** `stabilityai/stable-fast-3d`  
**License:** Community license — free if annual revenue < $1M USD  
**What it does:** Sub-1-second inference, UV-unwrapped textured mesh. Best speed/quality ratio for real-time applications. Already scaffolded in this codebase (`run_stablefast3d.py`).

---

### IFC Compliance note
None of these models output IFC natively. All output GLB or OBJ. IFC compliance is achieved downstream via IfcOpenShell, which wraps the mesh geometry into an IFC entity (IfcFurnishingElement, IfcBuildingElementProxy, etc.). This is already implemented in our pipeline. The models above all produce meshes that are geometrically cleaner than TripoSR, making the IFC wrapping more accurate.

---

## 2. Exporting Inventory to a Public xeokit Web Viewer

**Reference target:** https://xeokit.github.io/xeokit-sdk/examples/buildings/#xkt_dtx_HolterTower

The HolterTower example uses **XKT format** — xeokit's compressed binary format. It is loaded via `XKTLoaderPlugin`, not `GLTFLoaderPlugin`. XKT is ~10x smaller than IFC and loads in the browser in <1s for large buildings.

### Pipeline: our IFC → XKT → hosted xeokit viewer

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

**Step 3 — Create a standalone viewer HTML**

Create `viewer/index.html` that mirrors the HolterTower pattern:
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

**Step 4 — Add IFC→XKT conversion route to our Express server**
```js
// backend/routes/export.js — add endpoint
app.post('/api/export/xkt', async (req, res) => {
  const { ifcPath } = req.body;
  const xktPath = ifcPath.replace('.ifc', '.xkt');
  await exec(`ifc2xkt -s ${ifcPath} -o ${xktPath}`);
  res.json({ success: true, xktUrl: `/outputs/${path.basename(xktPath)}` });
});
```

**Step 5 — Deploy**

For a public site identical to HolterTower:
- Any static host works (Netlify, GitHub Pages, Vercel — all free)
- The `.xkt` file and the viewer HTML are the only files needed
- No server required for viewing (XKT is served as a static file)

---

## 3. AI for Office Spatial Positioning

**Goal:** Given a room outline and a list of detected furniture items (chairs, desks, monitors, printers, cupboards), automatically place them in positions that satisfy office ergonomics and regulatory standards.

### Standards that must be encoded

| Standard | Key rules |
|----------|-----------|
| OSHA 29 CFR 1910 | Min 4.65 m² (50 sq ft) per workstation; aisles ≥ 1.12m |
| ADA Standards | Accessible route ≥ 914mm; accessible workstation at each type |
| ISO 9241-5 | Monitor 50–70cm from eyes; screen top at or below eye level |
| NFPA 101 (Life Safety) | Clear path to exit at all times; no obstruction of egress |
| BIFMA G1 | Ergonomic guidelines for office seating and desk heights |

### Recommended AI algorithms (free, open source)

**Option A — ATISS (Autoregressive Transformers for Indoor Scene Synthesis)**
- License: MIT ✅
- GitHub: https://github.com/nv-tlabs/ATISS
- What it does: Given a room polygon, autoregressively places furniture objects one at a time using a transformer trained on real indoor layouts (3D-FRONT dataset)
- Strength: Learned real-world spatial distributions — chairs cluster around desks, printers near walls, etc.
- Limitation: Trained on home/residential scenes; needs fine-tuning on office layouts (3D-FRONT has office subset)

**Option B — DiffuScene**
- License: MIT ✅
- GitHub: https://github.com/tangjiapeng/DiffuScene
- What it does: Diffusion model over furniture placements — generates all object positions simultaneously (not autoregressive). Better for dense office layouts.
- Strength: Globally coherent layouts; handles many objects at once

**Option C — Rule-based constraint solver (no training required)**
- Libraries: scipy.optimize, OR-Tools (Google, Apache 2.0), PuLP
- What it does: Encodes all the standards above as hard constraints and an objective function (maximize workstation count, minimize wasted space), then solves
- Strength: Deterministic, always compliant, auditable
- Limitation: Layouts can feel rigid/mechanical compared to learned models

**Recommended approach: Rule-based constraints + ATISS refinement**

```
Room polygon + furniture list
        │
        ▼
Rule-based solver (OR-Tools)
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

### Dataset for training/fine-tuning ATISS on office layouts
- **3D-FRONT** — 18,800 professional interior designs including offices (free for research and commercial use with registration): https://tianchi.aliyun.com/specials/promotion/alibaba-3d-future
- **OpenXR Office Dataset** — synthetic office scenes

---

## 4. Team Structure

### Member 1 — Engineering lead (coding-intensive)

**Responsibilities:**
- Implement new AI model adapters (TRELLIS, real InstantMesh, Hunyuan3D-2)
- Build XKT export pipeline and hosted viewer
- Integrate spatial positioning solver (OR-Tools + ATISS)
- Backend API development
- Git management and CI

**Daily workflow:**
1. Pull from `main`
2. Create feature branch (`feat/trellis-adapter`, `feat/xkt-export`, etc.)
3. Implement, test locally
4. Open PR → other member reviews description
5. Merge to `main`

---

### Member 2 — Research and data lead (research/testing)

**Responsibilities:**
- Test each AI model with diverse office furniture photos (chairs, desks, monitors, printers, cupboards)
- Document output quality per model per object type (scoring grid)
- Collect and curate training data for ATISS fine-tuning (3D-FRONT office subset)
- Encode office standards (OSHA, ADA, ISO 9241) into constraint specification documents
- Validate IFC exports open correctly in Revit/AutoCAD/BIM viewers
- Write test scripts that run the pipeline end-to-end and compare outputs

**Daily workflow:**
1. Pull from `main`
2. Run test image batches through the pipeline using the test scripts
3. Log results in `tests/results/` (scores, screenshots, timings)
4. File GitHub Issues for any failures or quality regressions
5. Update documentation and constraint specs

---

## 5. Free VS Code-Compatible Software Stack

### For both members

| Tool | Type | Why | Install |
|------|------|-----|---------|
| **VS Code** | IDE | Primary editor | code.visualstudio.com |
| **GitLens** | VS Code ext | Full git history, blame, branches | VS Code Marketplace |
| **GitHub Pull Requests** | VS Code ext | Review PRs without leaving VS Code | VS Code Marketplace |
| **Prettier** | VS Code ext | Auto-format JS/TS/JSON | VS Code Marketplace |
| **ESLint** | VS Code ext | JS linting | VS Code Marketplace |
| **Python (Microsoft)** | VS Code ext | IntelliSense, debugging | VS Code Marketplace |
| **Pylance** | VS Code ext | Fast Python type checking | VS Code Marketplace |
| **Jupyter** | VS Code ext | Run notebooks inside VS Code | VS Code Marketplace |
| **Thunder Client** | VS Code ext | REST API testing (Postman alternative) | VS Code Marketplace |
| **Docker** | VS Code ext | Container management | VS Code Marketplace |

### For Member 1 (engineering)

| Tool | Type | Why | License |
|------|------|-----|---------|
| **Continue.dev** | VS Code ext | Free open-source AI coding assistant; works with local Ollama models or Claude API | Apache 2.0 |
| **Codeium** | VS Code ext | Free AI autocomplete (no revenue cap for individuals) | Free |
| **REST Client** | VS Code ext | Send HTTP requests directly from `.http` files | MIT |
| **Error Lens** | VS Code ext | Inline error highlighting | MIT |
| **GLSL Lint** | VS Code ext | WebGL shader validation | MIT |
| **Blender** *(separate app)* | 3D editor | Inspect/fix generated meshes manually; Python-scriptable | GPL (free) |

### For Member 2 (research/data)

| Tool | Type | Why | License |
|------|------|-----|---------|
| **Label Studio** | Web app (runs locally) | Annotate images for segmentation training; VS Code terminal launch | Apache 2.0 |
| **DVC** | VS Code ext + CLI | Data version control — track model weights and datasets like git | Apache 2.0 |
| **CSV to Table** | VS Code ext | View test result CSVs as formatted tables | MIT |
| **Markdown Preview Mermaid** | VS Code ext | Render diagrams in markdown docs | MIT |
| **Weights & Biases** *(free tier)* | Web dashboard | Track experiment runs, compare model outputs, log metrics | Free tier |
| **Meshlab** *(separate app)* | 3D mesh inspector | Open and inspect GLB/OBJ output quality without code | GPL (free) |

### Collaboration

| Tool | Why | Cost |
|------|-----|------|
| **GitHub** | Code, PRs, Issues, Projects board | Free |
| **GitHub Projects** | Kanban board for task tracking | Free |
| **GitHub Discussions** | Async Q&A and decisions | Free |
| **Hugging Face Spaces** | Host demo of the pipeline publicly | Free tier |

---

## 6. Full Implementation Plan (Phase 2)

Builds directly on the existing Phase 1 infrastructure. No existing files are removed or replaced — only additions and extensions.

---

### Sprint 1 — Real InstantMesh integration (Week 1–2)
**Owner:** Member 1 implements | Member 2 tests

The current `run_instantmesh.py` uses a depth-map placeholder. Replace with the real model.

- [ ] Download InstantMesh weights: `TencentARC/InstantMesh` (~5GB)
- [ ] Rewrite `backend/python-scripts/run_instantmesh.py` to call the real Zero123++ + LRM pipeline
- [ ] Add `zero123plus` and `einops` to requirements
- [ ] Test with 10 office objects (Member 2), document quality vs TripoSR
- [ ] Merge to `main`

---

### Sprint 2 — TRELLIS integration (Week 2–3)
**Owner:** Member 1 implements | Member 2 stress-tests

TRELLIS is the highest-quality available model. Needs memory optimization for the RTX 4050's 6GB VRAM.

- [ ] Clone TRELLIS repo into `backend/trellis/`
- [ ] Install dependencies: `pip install git+https://github.com/Microsoft/TRELLIS`
- [ ] Create `backend/python-scripts/run_trellis.py`
- [ ] Add memory optimization: `torch.cuda.empty_cache()`, chunked rendering
- [ ] Add TRELLIS as fourth option in frontend model selector
- [ ] Wire up `backend/ai/trellis.js` adapter
- [ ] Member 2: test 20 photos, score quality on 1–10 scale, log to `tests/results/trellis_quality.csv`

---

### Sprint 3 — XKT export and hosted viewer (Week 3–4)
**Owner:** Member 1 builds pipeline | Member 2 validates in Revit/BIM tools

- [ ] Install `@xeokit/xeokit-convert` globally
- [ ] Add `POST /api/export/xkt` endpoint to `backend/routes/export.js`
- [ ] Create `viewer/` directory with standalone xeokit HTML viewer (XKTLoaderPlugin)
- [ ] Add "Export to XKT" button to frontend beside the existing IFC export button
- [ ] Add Express route to serve `viewer/index.html` at `/viewer`
- [ ] Member 2: open exported XKT files in a hosted xeokit viewer and verify geometry
- [ ] Deploy static viewer to GitHub Pages or Netlify (free)

---

### Sprint 4 — Office object detection and classification (Week 4–5)
**Owner:** Member 2 curates dataset | Member 1 wires the classifier

Before we can place objects spatially, we need to know what each detected object is.

- [ ] Member 2: collect 200 labeled images of: chairs, desks, monitors, printers, cupboards, tables (use Label Studio)
- [ ] Fine-tune YOLOv8 classification head on these categories (`yolov8n-cls.pt` as base)
- [ ] Member 1: update `inference_base.py` to return object category label alongside the mesh
- [ ] Store category in the GLB metadata and pass through to IFC (`IfcChair`, `IfcDesk`, etc.)

---

### Sprint 5 — Spatial positioning engine (Week 5–7)
**Owner:** Member 1 builds solver | Member 2 encodes standards and validates

- [ ] Install OR-Tools: `pip install ortools`
- [ ] Member 2: write `docs/OFFICE_STANDARDS.md` — all OSHA/ADA/ISO 9241/NFPA rules as structured constraint specifications
- [ ] Member 1: create `backend/python-scripts/spatial_solver.py`
  - Input: room polygon (list of wall vertices), list of objects with categories and dimensions
  - Output: list of (object_id, x, y, z, rotation_y)
  - Hard constraints: aisle widths, egress paths, ADA clearances
  - Soft objective: maximize workstation density, cluster chairs to desks
- [ ] Add `POST /api/layout/auto` endpoint
- [ ] Frontend: "Auto-arrange" button that calls the endpoint and applies returned transforms in xeokit
- [ ] Member 2: validate 5 generated layouts against the standards spec, file issues for any violations

---

### Sprint 6 — ATISS fine-tuning on office layouts (Week 7–9)
**Owner:** Member 2 prepares data | Member 1 trains and integrates

- [ ] Member 2: download 3D-FRONT office subset, convert to ATISS training format
- [ ] Member 1: fine-tune ATISS for 50 epochs on office layouts (Google Colab free tier or local GPU)
- [ ] Replace rule-only solver with ATISS + constraint validation pass
- [ ] Member 2: compare 10 auto-generated layouts vs 10 rule-solver-only layouts (quality scoring)

---

### Sprint 7 — Hunyuan3D-2 integration (Week 9–10)
**Owner:** Member 1 | Member 2 tests texture quality

Hunyuan3D-2 is the best PBR texture output. Needs 24GB VRAM ideally — run via quantized version or Hugging Face Inference API if local VRAM insufficient.

- [ ] Evaluate whether RTX 4050 (6GB) can run quantized Hunyuan3D-2 mini variant
- [ ] If yes: integrate locally; if no: wire Hugging Face Inference API endpoint
- [ ] Create `backend/python-scripts/run_hunyuan3d.py`
- [ ] Add Hunyuan3D as model option in frontend
- [ ] Member 2: document texture quality improvement vs TripoSR in `tests/results/`

---

### Sprint 8 — Polish, testing, public demo (Week 10–12)

- [ ] Member 1: end-to-end integration test — upload photo → AI model → xeokit → IFC → XKT → hosted viewer
- [ ] Member 2: write user-facing documentation for the full workflow
- [ ] Member 2: create test suite with 30 diverse office objects, run all 4 models, compile quality comparison table
- [ ] Member 1: containerize with Docker for reproducible setup
- [ ] Deploy hosted demo to Hugging Face Spaces (free, shows the pipeline publicly)
- [ ] Final commit with updated README and full documentation

---

## 7. File additions (nothing existing is deleted)

```
3DpicToIFCModeling/
├── backend/
│   ├── trellis/                        ← NEW: TRELLIS source
│   ├── ai/
│   │   └── trellis.js                  ← NEW: TRELLIS adapter
│   └── python-scripts/
│       ├── run_trellis.py              ← NEW: TRELLIS inference
│       ├── run_hunyuan3d.py            ← NEW: Hunyuan3D-2 inference
│       └── spatial_solver.py          ← NEW: OR-Tools layout engine
├── viewer/
│   └── index.html                      ← NEW: standalone XKT viewer
├── tests/
│   ├── run_all_models.py               ← NEW: batch quality test script
│   └── results/                        ← NEW: CSV quality logs
├── docs/
│   └── OFFICE_STANDARDS.md             ← NEW: constraint specifications
└── DEVELOPMENT_ROADMAP_PHASE2.md       ← THIS FILE
```

---

## 8. Summary table

| Item | Status | Owner | Sprint |
|------|--------|-------|--------|
| Real InstantMesh weights | Planned | M1+M2 | 1 |
| TRELLIS integration | Planned | M1+M2 | 2 |
| XKT export + hosted viewer | Planned | M1+M2 | 3 |
| Object classification (YOLO fine-tune) | Planned | M2+M1 | 4 |
| Spatial positioning (OR-Tools) | Planned | M1+M2 | 5 |
| ATISS office fine-tuning | Planned | M2+M1 | 6 |
| Hunyuan3D-2 integration | Planned | M1+M2 | 7 |
| Public demo deploy | Planned | M1+M2 | 8 |
| TripoSR pipeline (GPU) | ✅ Done | — | Phase 1 |
| xeokit viewer | ✅ Done | — | Phase 1 |
| IFC export | ✅ Done | — | Phase 1 |
| YOLO segmentation | ✅ Done | — | Phase 1 |
