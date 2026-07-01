# 3DpicToIFCModeling — Roadmap & Status

**Branch:** `app-development` · **Last updated:** 2026-07-01
Legend: ✅ done · 🔜 next · 🧊 backlog · ⚠️ known issue

---

## ✅ Done

### Core pipeline (photo → 3D → IFC → BIM)
- ✅ Detect (DETR) → metric size (Depth-Anything-v2) → retrieve (DINOv2 over ABO) / generate (TripoSR)
- ✅ IFC4 export (IfcOpenShell) with real geometry + Project/Site/Building/Storey hierarchy
- ✅ xeokit viewer (GLB), IFC→XKT/GLB paths, Autodesk-Viewer QA
- ✅ 5-generator benchmark (H200): F-score/Chamfer, gallery, best-of-each asset library
- ✅ Inventory (accumulate across photos) + 3 export modes (together / each / table)
- ✅ Export-IFC fixes (Windows path bug, export-from-generated-objects)
- ✅ UI: Bildungscampus / Dieter Schwarz Stiftung dark theme

### Building-scale population (this phase)
- ✅ **Load a real architectural IFC** (Duplex: 21 rooms, walls, doors) as the container — the tool
  supplies furniture, not architecture
- ✅ **Read rooms straight from the IFC** (`IfcSpace` name + footprint) — no segmentation needed
- ✅ **Space-aware smart furnishing** — each room measured (type + area) → a sensible fitting set
  (Neufert ~6.5 m²/workstation; seating/beds/cabinets scale by area)
- ✅ **Obstacle-aware ergonomic placement** — CP-SAT solver (Neufert/Panero/ADA clearances) routes
  furniture *around* internal walls, beams, columns, doors; overlapping obstacles merged (shapely);
  fit-as-many-as-possible → **0 clashes** (Duplex verified)
- ✅ **Manual per-room choice (#1)** — building selector + per-room editable furniture chips
- ✅ **Click-drag reposition (#2)** — each piece a separate movable object; pick + drag on floor +
  Save layout → downloadable GLB
- ✅ **Upload-your-own generated items (#3)** — drop a `.glb`/`.ifc`, auto-categorized, shown with an
  "OURS" badge in the picker
- ✅ Standalone xeokit building viewers (empty shell, populated, SCS office complex)

### Docs
- ✅ `FOUNDATION_FOR_RESEARCH_PAPER.md` (paper), `README.md` (building section), `ROADMAP.md` (this),
  `DEMO_RUNBOOK.md`, memory of the architecture-vs-furniture lesson

---

## 🔜 Next

- 🔜 **Non-rectangular room clipping** — clip furniture to the true `IfcSpace` polygon, not just its
  bounding box (shapely is already a dependency)
- 🔜 **IFC round-trip of edits** — re-export the *dragged* / manually-chosen building back to IFC4
  (currently Save produces a GLB; add the IFC writer path via `build_building_ifc`)
- 🔜 **Binary XKT** — install `@xeokit/xeokit-convert` so building/IFC load 10–100× faster than the
  JSON fallback
- 🔜 **Verify drag UX** on real hardware; add a move/rotate gizmo + snap-to-grid if needed
- 🔜 **More buildings** in the selector (beyond the Duplex) + upload-your-own building IFC

---

## 🧊 Backlog

- 🧊 Real-world scale + PCA up-axis auto-orientation for generated meshes (fix size/orientation outliers)
- 🧊 Viewer geometry **instancing** (xeokit SceneModel) for very large buildings
- 🧊 Benchmark TRELLIS.2-4B (MIT, the clean untested gap)
- 🧊 PySide desktop `.exe` embedding the web UI
- 🧊 Auth + HTTPS before any hosting; upload validation hardening

---

## ⚠️ Known issues

- ⚠️ **Live "Generate" (photo→mesh) segfaults after heavy use** on the 6 GB GPU (`0xC0000005` on GPU
  *and* CPU) — needs a **machine reboot**. All CPU building/IFC tools are unaffected.
- ⚠️ XKT export is a JSON fallback (see Binary XKT above).
- ⚠️ Rooms are treated as bounding boxes (see Non-rectangular clipping above).

---

## Quick start (apps)

| URL | What |
|-----|------|
| `localhost:8000` | Selection room-builder + **building population** (pick building → per-room furniture → populate → **drag** → save) + **upload-your-own** items |
| `localhost:3000` | Photo→3D→IFC generator (⚠️ live Generate needs a reboot) |
| `localhost:3000/populated_building_viewer.html` | Duplex auto-populated (space-aware, 0 clashes) |
| `localhost:3000/empty_building_viewer.html` | Empty Duplex shell |
| `localhost:8900` | 5-model comparison gallery |

```bash
python backend/app_server.py     # the :8000 app (building population + upload)
node backend/server.js           # the :3000 generator app
python backend/python-scripts/populate_building.py sample_buildings/Duplex_Architecture.ifc out.glb   # CLI populate
```
