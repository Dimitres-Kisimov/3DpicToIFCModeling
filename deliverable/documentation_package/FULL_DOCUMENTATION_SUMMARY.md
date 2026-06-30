<!--
HOW TO USE THIS DOCUMENT
This is a complete, self-contained content brief for the 3DpicToIFCModeling project.
Feed it to a slide/design tool (Gamma, Beautiful.ai, Tome, Claude artifacts) or a designer
to produce a polished deck or report. All numbers are real and verified.

- Every figure is referenced as `doc_assets/<file>.png` — those images ship alongside this file.
- A SUGGESTED SLIDE STRUCTURE and a full IMAGE MANIFEST are at the end.
- The project is bilingual-friendly (German/English); content here is English — translate as needed.
- Two presenters: Part 1 = Gülriz (analytical), Part 2 = Dimitrius (technical).
-->

# From Photo to BIM — AI Room Population & Photo→3D Pipeline
### 3DpicToIFCModeling · SCS · 2026-06-23

**One line:** Photograph office objects → match each to a clean catalog mesh → an AI arranges
them in a room the human way → export an IFC/BIM model, a 3D scene, and an object schedule.

---

## 1. Executive summary
- A **retrieval-and-layout** pipeline that turns photos of office furniture into a valid, exportable
  BIM scene — *without* relying on error-prone single-image 3D generation.
- Backed by **400 real product meshes** (Amazon Berkeley Objects, CC-BY-4.0) matched via DINOv2 + FAISS.
- A **functional layout engine** (ergonomic rule packs + CP-SAT solver + furniture anchoring) places
  furniture the way a human would — chairs facing desks, storage on walls, circulation kept clear —
  verified correct **to the centimetre**.
- A working **web app**: pick items → generate layout → 3D preview → export CSV / GLB / IFC4.
- We **quantified the single-view 3D ceiling**: TripoSR reconstructions score precision ~0.81 but
  recall ~0.09 — they capture the visible surface, miss the unseen back.
- Commercial-safe throughout: **€0 licence royalties**, **~€185/month** infra, **<€0.02/room** at scale.
- Hero image: `doc_assets/results_plate.png` (everything at a glance).

---

## 2. The problem — why naïve single-photo → BIM fails
Single-image 3D reconstruction is **mathematically ill-posed**; four structural failures that no model
switch can fix:
1. **Asymmetric legs** — no symmetry prior; each leg drifts from a noisy latent.
2. **Hallucinated back/underside** — one photo carries zero info about hidden surfaces.
3. **Non-deterministic** — same photo, different mesh each run (unusable for a reusable catalog item).
4. **Noisy topology** — holes, non-manifold edges.

And fundamentally: **a mesh is not a semantic IFC model.** IFC needs typed objects + dimensions +
relationships, not a triangle soup. → *Reframe: classify + retrieve a clean known mesh, don't generate.*

---

## 3. The approach — retrieval + functional layout
- **Photo → object table.** Each detected object becomes a row: type, real size, material, 3D model,
  IFC class, source/licence. The table is the single source of truth.
- **Retrieval, not generation.** DINOv2 embedding + FAISS nearest-neighbour over the 400-mesh catalog
  returns a clean, real, repeatable product mesh. Generation (TripoSR/SAM 3D) is a *fallback* only.
- **Functional layout.** A solver arranges the retrieved meshes ergonomically and exports IFC.
- Image: `doc_assets/fig00_overview.png` (scenes overview).

---

## 4. The 400-item catalog
- **Amazon Berkeley Objects (ABO)** — real Amazon products as 3D meshes. **400 total, 8 categories × 50**:
  desk, office_chair, cabinet, bookshelf, sofa, table, stool, lamp.
- Licence **CC-BY-4.0** (commercial-safe, per-item ASIN attribution).
- **Real metric dimensions** per mesh (e.g., desk 0.74×1.4×0.7 m; chair 1.10×0.6×0.6 m), 1k–70k faces.
- **DINOv2 + FAISS** retrieval; an in-app **per-item picker** with colored previews lets a user choose
  the exact mesh.
- Images: `doc_assets/catalog_office_chair.png`, `catalog_desk.png`, `catalog_sofa.png`, … (8 colored sheets).

---

## 5. The layout engine — three layers (the technical core)
**Layer 1 — Ergonomic rule packs** (encoded from published standards):
- Neufert: ~6 m²/workstation, ≥1.0 m circulation aisle.
- ADA: 0.915 m route, 0.815 m door clear, 1.525 m turning circle.
- IBC/IFC: 0.90 m door keep-clear (never blocked). Per-item clearances (chair 0.10 m, cabinet 0.20 m).
- A *room type* (office / living / workspace) = a profile of these numbers + functional groups.

**Layer 2 — Constrained packing (Google OR-Tools CP-SAT):**
- 10 cm grid, 0°/90° rotations, `AddNoOverlap2D` across furniture + fixed obstacles (columns, doors).
- **Wall-affinity objective**: storage hugs the perimeter → the centre stays open for circulation.

**Layer 3 — Functional anchoring + seat-facing:**
- Children (chair, monitor, lamp) folded into a desk's reserved footprint → groups never collide.
- Each chair's forward direction is **inferred from its own mesh geometry** and rotated to face the desk.
- **Verified to the centimetre**: a hand-traced workstation matched the solver's output exactly.
- Images: `doc_assets/fig01_office_single_montage.png`, `fig02_office_team_montage.png`.

---

## 6. Constraints, accessibility & generalization
- **Obstacles + doors** respected: `doc_assets/fig03_office_obstacles_montage.png` (column hatched, door keep-clear blue).
- **ADA mode**: wider aisles — `doc_assets/fig04_office_ada_montage.png`.
- **Room-type generalization**: `doc_assets/fig05_living_room_montage.png` (living) and
  `doc_assets/fig06_workspace_dense_montage.png` (dense workspace).

---

## 7. Capacity boundary (the "space limit", quantified)
- For each room size, the largest number of full workstations the solver can place before infeasible:
  **4×3 m → 2 · 5×4 m → 3 · 6×5 m → 4 · 8×6 m → 6.** Scales with floor area.
- The solver reports infeasible rather than producing invalid overlaps.
- Image: `doc_assets/fig08_capacity_sweep.png` (green/red feasibility grid).
- Overpacked example: `doc_assets/fig07_office_overpacked_montage.png`.

---

## 8. The web app
- **Flask** backend + **xeokit** WebGL 3D viewer.
- Flow: **pick** (category + count, or per-item picker) → **Generate** (CP-SAT solve) → **preview**
  (3D + object table) → **Export** (CSV / GLB / IFC4).
- **Ephemeral**: generation writes only a scratch preview; **nothing is saved until you Export**.
- Degrades gracefully when WebGL is unavailable (table + exports still work).

---

## 9. Accuracy evaluation — measuring the single-view ceiling
**Method (ABO-as-ground-truth):** we own the meshes, so render one → reconstruct → compare to the
known original. Normalise (unit bbox-diagonal) + multi-seed ICP align; metrics = **Chamfer distance**
and **F-score @ τ=0.02** (precision = recon near GT, recall = GT covered). Seeded → reproducible.
- **Calibration (self-test):** identity F=1.00, noisy-1% F=0.99, **different object F=0.18** — monotone, discriminating.
- **TripoSR baseline (3 chairs):** mean **Chamfer 0.169**, **F-score 0.155**, **precision ~0.81**, **recall ~0.09**.
- **Finding:** high precision, low recall = the visible surface is captured, the unseen back is missed.
  Good for client visualisation, **not** BIM-grade geometry. The route past it is **multi-view + scale calibration**.
- Image: `doc_assets/fig09_accuracy_triposr.png` (left: error vs reference; right: precision ≫ recall).
- **Next:** same metric scores all four generators (TripoSR / InstantMesh / TRELLIS / SAM 3D) on a RunPod A40 (~$10).

---

## 10. Energy & cost
- **German electricity (Baden-Württemberg, 2026):** €0.25/kWh.
- **GPU power:** ~0.45–0.6 kW × 24/7 ≈ 324–432 kWh/month → **€80–108/month** electricity.
- **Hosting:** Hetzner GEX44 **€184/month** (GDPR-clean, German DC), or on-prem Heilbronn ~€175/month.
- **Per-room cost:** ~€0.019 at 10,000 rooms/month, falling further at scale.
- **Licence royalties: €0 — forever** (all components MIT / Apache-2.0 / CC-BY).
- Levers: self-host open models + Mistral LLM → no per-call tax; OR-Tools on CPU = free; Cloudflare R2 → €0 egress.

---

## 11. AI models & licences (the survey)
Retrieval-first stack — all commercial-safe on HuggingFace:
| Role | Model | Licence | VRAM |
|---|---|---|---|
| Retrieval (primary) | DINOv2-Large (`facebook/dinov2-large`) | Apache-2.0 | ~1.5 GB |
| Detection | Grounding DINO base | Apache-2.0 | ~3 GB |
| Segmentation | SAM 2.1 hiera-large | Apache-2.0 | ~3 GB |
| Depth / metric scale | Depth Anything V2 **Small** | Apache-2.0 | ~0.5 GB |
| 3D fallback (best) | SAM 3D Objects (`facebook/sam-3d-objects`) | SAM license (commercial OK) | ~24 GB |
| 3D fallback (PBR) | Stable Fast 3D | Stability (free <$1M rev) | ~7 GB |
| 3D fallback | TRELLIS-image-large | MIT | ~16 GB |
| 3D fallback | TripoSR | MIT | ~4 GB |

**Licence traps to AVOID:** Hunyuan3D-2 (excluded in the EU), YOLOv8 (AGPL copyleft), Depth Anything
**Base/Large** (CC-BY-NC — only *Small* is Apache), Stable Fast 3D above $1M revenue.
**Principle:** SCS sells *outputs* (IFC files), not model weights — so permissive licences impose nothing.

---

## 12. Outcomes & roadmap
**Done:** retrieval + functional layout system; 400-item catalog with colored picker; web app with
IFC/CSV/GLB export; accuracy harness + the single-view ceiling quantified; reproducible figure set;
updated paper + cost model.
**Next:** run the 4-way bake-off (RunPod); wire photo→retrieval into the app; **multi-view + scale
calibration** (the real route to metric accuracy); IFC4 validation; desktop (PySide) build.

---

# SUGGESTED SLIDE / SECTION STRUCTURE (for the styling tool)
1. Title — From Photo to BIM (hero: `results_plate.png`)
2. Executive summary (4–5 bullets + key numbers)
3. The problem — single-view limits (4 points)
4. The approach — retrieval + layout (`fig00_overview.png`)
5. The 400-item catalog (`catalog_office_chair.png` montage)
6. Layout engine — 3 layers (`fig01_office_single_montage.png`)
7. Layout in action (`fig02_office_team_montage.png`)
8. Constraints + ADA (`fig03…` + `fig04…`)
9. Generalization (`fig05…` + `fig06…`)
10. Capacity boundary (`fig08_capacity_sweep.png`)
11. The web app (UI flow)
12. Accuracy — method + result (`fig09_accuracy_triposr.png`)
13. Energy & cost (the € table)
14. Models & licences (the table)
15. Outcomes & roadmap

---

# IMAGE MANIFEST — every asset, with caption & suggested use
All files are in the `doc_assets/` folder shipped with this document.

| File | Caption | Use on |
|---|---|---|
| `results_plate.png` | Composite of all results (layouts a–g, capacity h, accuracy i) | Title / overview |
| `fig00_overview.png` | All layout scenes at a glance | Approach |
| `fig01_office_single_montage.png` | Single workstation: chair faces desk; monitor/lamp on desk | Layout engine |
| `fig02_office_team_montage.png` | 3-workstation office: chairs face desks, storage on walls, centre open | Layout in action |
| `fig03_office_obstacles_montage.png` | Column + door keep-clear respected | Constraints |
| `fig04_office_ada_montage.png` | ADA accessibility — wider aisles | Accessibility |
| `fig05_living_room_montage.png` | Living-room rule pack (different groups) | Generalization |
| `fig06_workspace_dense_montage.png` | Dense workspace variant | Generalization |
| `fig07_office_overpacked_montage.png` | Overpacked → correctly infeasible | Feasibility |
| `fig08_capacity_sweep.png` | Capacity boundary: room size × workstations | Capacity |
| `fig09_accuracy_triposr.png` | Photo→3D accuracy: precision ≫ recall (single-view ceiling) | Accuracy |
| `catalog_office_chair.png` … (8 sheets) | Colored catalog previews per category (50 of 400) | Catalog |
| `figNN_*_plan.png` / `_3d.png` | Per-scene floor plan / colored 3D (alternatives to the montages) | Optional detail |

_Each layout figure also has separate `_plan.png` (top-down) and `_3d.png` (colored 3D) versions in
`doc_assets/` if you prefer to show them individually rather than the side-by-side montage._
