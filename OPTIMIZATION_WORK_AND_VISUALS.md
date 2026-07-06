# Optimization Work + Visual Links

**Branch:** `redesign-generator-ui` · **Updated:** 2026-07-06
**Scope:** UI redesign, viewer fixes, mesh-cleanup algorithm, IFC-level optimizer, batch test, and all
visual comparison pages. All pages are served by the Node app on **http://localhost:3000/**.

> ⚠️ The `localhost:3000` links only work while the app is running. Start it with
> `node backend/server.js` (or the detached launch in the run section). Each link's source file is a
> committed `.html` in `frontend/`, so it is preserved in the repo even when the server is off.

---

## 1. What we did this session

1. **Redesigned the generator UI (`:3000`)** — removed the Bildungscampus logo, simple end-user
   layout, plain-language steps, a **"View your IFC" step linking viewer.autodesk.com**, cache-busting.
2. **Fixed the 3D viewer** — orbit + zoom-to-cursor, reliable `flyTo(model)` fit, upright orientation
   (X-euler spin), **Fit view / Rotate** buttons, working **Clear view** (destroys `scene.models`),
   removed the click-highlight + transform panel for a clean end-user view.
3. **Mesh cleanup algorithm** (`clean_and_optimize.py`) — removes TripoSR's random spikes/holes/debris
   and optimizes the mesh; **color preserved**.
4. **IFC-level optimizer** (`optimize_ifc.py`) — the executive's objective: an algorithm that runs **on
   the IFC data**, on any object(s), in **one pass** (no double-processing).
5. **Batch-tested** both across 10 furniture items and built **side-by-side visual comparisons.**
6. Proved empirically: the quality ceiling is **TripoSR's generation**, not the post-processing; and
   that **no extra mesh algorithms** meaningfully help (the meshes are already watertight/welded).

---

## 2. The algorithms

### Mesh cleanup — one shared function `clean_mesh()` (used by GLB export AND the IFC optimizer)
1. **Debris/spike removal** — connected-component split, drop components < 0.6% of faces (kills stray
   lines/spikes/floaters, keeps body + legs).
2. **Watertight repair** — **MeshFix** (Attene): fills holes, joins components, fixes non-manifold.
3. **Taubin smoothing (λ|μ)** — volume-preserving denoise (won't shrink like Laplacian).
4. **Quadric-error decimation** (Garland–Heckbert) — reduce to a face budget.
5. Ground/centre + **colour preserved** (capture PBR `baseColorFactor`, re-apply).

### IFC optimizer `optimize_ifc.py` — one pass, no repetition
- **Clean each *unique* mesh ONCE** (geometry-hash cache) — a building with 8 identical chairs cleans
  the chair mesh 1×, not 8×.
- **Instancing** — identical `IfcTriangulatedFaceSet`s collapsed to one shared entity (store once,
  reference N times). All objects kept.
- **Precision rounding** (CoordList → 4 dp = 0.1 mm) + optional **gzip (.ifcZIP)**.
- Writes optimized IFC + before/after report. Hierarchy/placement/metadata preserved.

---

## 3. Results (batch, 10 items, one example each)

| | Mesh cleanup | IFC optimizer |
|---|---|---|
| **Total** | 800,840 → 147,392 faces (**−82%**), 15.1 MB → 2.6 MB (**−83%**) | 26.9 MB → 4.1 MB (**−85%**) |
| Per-item | ~65–90% each (except `lamp`, already light → ~1%, correctly untouched) | ~70–90% each |
| Single office chair | 85,500 → 15,000 faces | 2.8 MB → 423 KB IFC (gzip 136 KB) |

---

## 4. 🔗 Visual links (all preserved as `frontend/*.html`)

| Link | File | What it shows |
|------|------|---------------|
| http://localhost:3000/optimize_visual.html | `frontend/optimize_visual.html` | **Bar-chart visual** of mesh + IFC reduction per item |
| http://localhost:3000/optimize_test.html | `frontend/optimize_test.html` | **Numbers table** — mesh + IFC side by side, all 10 items |
| http://localhost:3000/gallery3d.html | `frontend/gallery3d.html` | **Live 3D gallery** of the 10 optimized furniture end-results |
| http://localhost:3000/four_way_all.html | `frontend/four_way_all.html` | **4-way for EVERY item** (dropdown): Original · IFC-optimized · Catalog · Mesh-optimized |
| http://localhost:3000/four_way.html | `frontend/four_way.html` | 4-way for the office chair only |
| http://localhost:3000/ifc_compare.html | `frontend/ifc_compare.html` | IFC **before/after** (chair) |
| http://localhost:3000/chair_compare.html | `frontend/chair_compare.html` | TripoSR raw vs cleaned vs **SAM 3D** (model-is-the-lever) |
| http://localhost:3000/chair_final.html | `frontend/chair_final.html` | Final optimized colored chair GLB |
| http://localhost:3000/ | `frontend/index.html` | The **redesigned generator app** |
| http://localhost:3000/populated_building_viewer.html | `frontend/populated_building_viewer.html` | Duplex auto-populated |
| http://localhost:3000/empty_building_viewer.html | `frontend/empty_building_viewer.html` | Empty Duplex shell |
| http://localhost:3000/building_viewer.html | `frontend/building_viewer.html` | SCS office complex |
| http://localhost:8000/ | `demo/app.html` | Building-population app (pick → furnish → drag → save) |
| http://127.0.0.1:8900/ | `deliverable/cloud_gallery/` | 5-model benchmark gallery |

---

## 5. Run everything (detached, persistent)
```powershell
$py="C:\Users\dimik\AppData\Local\Python\pythoncore-3.14-64\python.exe"; $node="C:\Program Files\nodejs\node.exe"; $repo="C:\Users\dimik\3DpicToIFCModeling"
Start-Process $node "backend\server.js" -WorkingDirectory $repo -WindowStyle Hidden          # :3000 (all the viewers above)
Start-Process $py  "backend\app_server.py" -WorkingDirectory $repo -WindowStyle Hidden        # :8000
Start-Process $py  "serve.py" -WorkingDirectory "$repo\deliverable\cloud_gallery" -WindowStyle Hidden  # :8900
```
**Re-run the optimization test:** `python backend/python-scripts/batch_optimize_test.py <model>`
**Optimize any IFC:** `python backend/python-scripts/optimize_ifc.py in.ifc out.ifc [--zip]`
**Clean any GLB:** `python backend/python-scripts/clean_and_optimize.py in.glb out.glb`

---

## 6. Key files
- `backend/python-scripts/clean_and_optimize.py` — `clean_mesh()` (shared cleanup) + GLB path
- `backend/python-scripts/optimize_ifc.py` — one-pass IFC optimizer (clean + instance + precision + zip)
- `backend/python-scripts/batch_optimize_test.py` — the 10-item batch test
- `frontend/*.html` — every visual page above (all committed)
- `TRIPOSR_CLEANUP_AND_TEST_LIST.md` — algorithm + 17-item shape test list

*All committed + pushed to `origin/redesign-generator-ui`.*
