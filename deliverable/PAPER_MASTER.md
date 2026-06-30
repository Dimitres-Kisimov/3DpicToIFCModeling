<!--
INSTRUCTIONS FOR THE GENERATING INSTANCE
Produce a single .docx research paper from this master document.
- Use the headings below as the document structure (Heading 1/2/3).
- Where a figure is referenced as [FIGURE: figures/<file>.png — caption], INSERT that image
  from the deliverable's figures/ folder, sized to page width, with the caption beneath it.
- Render all Markdown tables as Word tables. Keep numbers exactly as written.
- Title page: title + subtitle + author + date. Add an auto Table of Contents after the abstract.
- This supersedes the May 2026 critical-analysis paper; it folds in the implemented system
  and the new empirical results. Tone: academic, precise, honest about limitations.
-->

# From 2D Image to IFC-Ready BIM: A Retrieval-and-Layout Pipeline with a Quantified Single-View Ceiling

**Subtitle:** Implementation and empirical evaluation of an AI room-population system, and a measured account of why single-image 3D reconstruction is bounded.

**Author:** Dimitres Kisimov
**Affiliation:** SCS — 3DpicToIFCModeling Project
**Contact:** dinoslice26@gmail.com
**Date:** 23 June 2026 (supersedes the 5 May 2026 critical-analysis report)

---

## Abstract

We previously argued (May 2026) that single-view AI 3D reconstruction is fundamentally
unsuited to producing BIM-grade IFC geometry from photographs. This paper turns that
*assertion* into a *measurement*, and presents the corrected system built on the
recommendation that followed from it. We implement a **retrieval-and-layout** pipeline:
each photographed object becomes a row in an object table (type, real dimensions, material,
licence, 3D model), objects are matched to a catalogue of **400 real product meshes**
(Amazon Berkeley Objects, CC-BY-4.0), and a functional layout engine arranges them in a room
the way a human would — chairs facing desks, storage along walls, circulation kept clear —
before exporting an IFC4 model and an interactive 3D view. Separately, we build a
generator-agnostic accuracy harness (Chamfer distance + F-score against known ground truth)
and use our own catalogue meshes as ground truth to **quantify the single-view ceiling**:
TripoSR reconstructions achieve high surface *precision* (~0.81) but low *recall* (~0.09) —
the visible surface is captured, the unseen back is not. We report a reproducible figure set,
a production cost model, and the path past the ceiling (multi-view + scale calibration).

---

## 1. Introduction

Building Information Modeling (BIM) and its open exchange format, IFC, encode not just
geometry but semantics: object types, materials, spatial relationships. Automatically
producing BIM data from ordinary photographs would dramatically cut the cost of digitising
spaces and their contents. The 3DpicToIFCModeling project pursued this across multiple
phases, integrating single-image-to-3D models (TripoSR, InstantMesh, TRELLIS, SAM 3D),
a processing pipeline, and an IFC export layer.

Our earlier critical analysis concluded that the original premise — single-view AI
reconstruction → BIM-grade IFC — is categorically mismatched (Section 2). This paper acts on
that conclusion: it (i) implements the recommended **parametric/retrieval** approach as a
working system, (ii) adds a **functional room-layout** engine that the original pipeline
lacked, and (iii) replaces the qualitative "single-view is limited" claim with **hard,
reproducible numbers**.

## 2. Background: why the original approach failed (summary)

The May 2026 analysis identified four structural problems, summarised here:

1. **Wrong models for the task.** TripoSR/InstantMesh/TRELLIS are trained on consumer-object
   datasets (ShapeNet, Objaverse), optimised for visual plausibility, never on architectural
   or BIM-relevant geometry.
2. **Single-view is ill-posed.** One photograph carries no information about occluded
   surfaces, absolute scale, or non-visible topology; models hallucinate the rest.
3. **Mesh ≠ IFC.** IFC is a semantic data model (parametric walls, material layer sets,
   spatial containment), not a triangle soup. Wrapping a noisy mesh in IFC XML is
   syntactically valid but semantically empty.
4. **No semantics.** The pipeline could not answer "is this a wall or a column?" — the
   classification a BIM model requires.

The analysis recommended (its §7.3) **parametric template matching**: classify the object,
retrieve a parametric/known template, and adjust to the photograph — producing valid BIM data
without depending on geometric reconstruction. The present system implements exactly this.

## 3. System overview

[FIGURE: figures/results_plate.png — Results overview. (a–g) functional room layouts across criteria; (h) capacity boundary; (i) photo→3D accuracy (single-view ceiling). All panels are server-side renders generated reproducibly from the pipeline.]

The corrected pipeline is: **photograph → object table → retrieval to a real catalogue mesh →
functional layout → IFC4 + interactive 3D view → export.** The object table is the single
source of truth; the human exports from it (CSV / GLB / IFC) and an AI lays objects out
functionally. The stack is licence-clean throughout (Section 8).

## 4. Catalogue and data

The asset library is **Amazon Berkeley Objects (ABO)** — real Amazon products as 3D meshes —
**400 meshes across 8 office-furniture categories (50 each):** desk, office_chair, cabinet,
bookshelf, sofa, table, stool, lamp. Each carries provenance (source ASIN, product type, true
metric dimensions, face count, thumbnail) and the permissive **CC-BY-4.0** licence. Categories
without a native ABO mesh (filing cabinet, coffee table, side table, monitor) borrow a
visually-similar mesh or a clean procedural primitive. Retrieval matches a photographed object
to the nearest catalogue mesh via DINOv2 embeddings + a FAISS index.

## 5. Functional layout engine

The layout engine is what makes a populated room read as human rather than merely
non-overlapping. It has three layers:

1. **Rule packs** — ergonomic numbers from published standards encoded as data: Neufert
   (≈6 m²/workstation, ≥1.0 m circulation), Panero & Zelnik (seating clearances), ADA (0.915 m
   routes, 0.815 m door clear, 1.525 m turning circle), IBC/IFC (door keep-clear). A room type
   (office / living / workspace) is a profile of these numbers plus functional groupings.
2. **Constrained packing** — Google OR-Tools CP-SAT on a 10 cm grid, 0°/90° orientations,
   no-overlap across furniture and fixed obstacles (columns, door keep-clear zones), with a
   **wall-affinity objective** that pulls storage to the perimeter and keeps the centre open.
3. **Functional anchoring + seat-facing** — children (chair, monitor, lamp) are folded into a
   desk's reserved footprint so groups never collide, then placed relative to their anchor.
   Each chair's forward direction is **inferred from its own mesh geometry** and rotated to
   face the desk — robust to the catalogue mesh's authored orientation.

The engine was verified by tracing a workstation through all three layers by hand and
confirming the solver's output matched **to the centimetre**.

[FIGURE: figures/fig01_office_single_montage.png — Single workstation: chair auto-anchored in front of the desk and turned to face it; monitor and lamp on the desk surface.]

[FIGURE: figures/fig02_office_team_montage.png — Three-workstation office: each desk gets a facing chair and monitor; storage hugs the walls and the centre stays open for circulation.]

### 5.1 Constraint handling

[FIGURE: figures/fig03_office_obstacles_montage.png — The same office with a structural column and a door keep-clear zone: no furniture overlaps the obstacle and the door swing stays unblocked.]

[FIGURE: figures/fig04_office_ada_montage.png — ADA accessibility mode: wider aisles and door clearances applied for wheelchair circulation.]

### 5.2 Generalization across room types

[FIGURE: figures/fig05_living_room_montage.png — Living-room rule pack: different functional groups (coffee table in front of sofa, stools beside it) and tighter circulation than the office.]

[FIGURE: figures/fig06_workspace_dense_montage.png — Workspace variant (heavier storage, wider aisles) at higher density.]

### 5.3 Feasibility and capacity

[FIGURE: figures/fig07_office_overpacked_montage.png — Feasibility boundary: a deliberately overpacked small room. The solver reports infeasible rather than producing an overlapping (invalid) layout.]

[FIGURE: figures/fig08_capacity_sweep.png — Capacity boundary: for each room size, the largest number of full workstations the solver can place before it becomes infeasible. The boundary scales with floor area.]

## 6. Interactive application

A browser application (Flask backend, xeokit WebGL viewer) lets a user pick catalogue
categories and counts, set room size/type, generate the layout, inspect it in 3D, and export.
The preview is **ephemeral**: generation writes to a scratch area wiped on reset and on
startup; **nothing is saved until the user clicks Export** (CSV / GLB / IFC), which downloads
the artefact. The viewer degrades gracefully when WebGL is unavailable (the object table and
exports still work).

## 7. Quantifying the single-view ceiling

The May analysis *asserted* single-view reconstruction has a ceiling. We *measure* it.

### 7.1 Method (ABO-as-ground-truth)

Because we own 400 real meshes, we can render one to a synthetic photo, reconstruct it, and
compare the result to the **known original** — a clean ground-truth protocol most photo→3D
studies cannot run. Both meshes are normalised (centred, unit bounding-box diagonal) and the
reconstruction is aligned with multi-seed ICP (12 seed rotations × ICP, best kept). We then
compute, on seeded (reproducible) surface samples:

- **Chamfer distance** — mean bidirectional nearest-neighbour distance (lower is better);
- **F-score @ τ = 0.02** — precision/recall of points within τ of the other surface;
- **precision** = reconstruction near ground truth; **recall** = ground truth covered.

The metric is validated by a self-test on degraded meshes: identity F = 1.00, decimated-20×
F = 1.00, noisy-1% F = 0.99, a *different* object F = 0.18 — monotone and discriminating.

### 7.2 Result (TripoSR baseline)

End-to-end (render → TripoSR → score) on three office chairs, local RTX 4050:

| object | chamfer | F@0.02 | precision | recall | sec |
|--------|---------|--------|-----------|--------|-----|
| chair B07DBH52YB | 0.168 | 0.227 | 0.72 | 0.14 | 23 |
| chair B076HDDMKM | 0.165 | 0.087 | 0.88 | 0.05 | 13 |
| chair B075ZZYH4B | 0.175 | 0.151 | 0.84 | 0.08 | 12 |
| **mean** | **0.169** | **0.155** | **~0.81** | **~0.09** | |

[FIGURE: figures/fig09_accuracy_triposr.png — Single-image→3D accuracy (TripoSR vs ABO ground truth). Left: per-object Chamfer distance sits near the different-object reference, far above identity. Right: precision (~0.81) far exceeds recall (~0.09) — the single-view ceiling.]

**Interpretation.** Precision is high but recall is low: TripoSR reconstructs the *visible*
surface fairly accurately yet recovers only ~9% of the true surface — it cannot see the
back/sides from one photo. On coverage, a single-view reconstruction of the *correct* chair is
in the same regime as a *wrong* chair. This is usable for client visualisation, not for
BIM-grade geometry, exactly as the original analysis predicted — now with numbers. The same,
identical metric scores all four generators in the cloud bake-off (TripoSR / InstantMesh /
TRELLIS / SAM 3D); that comparison table is the next data point.

## 8. Licensing and production cost

The shippable stack is **MIT / Apache / BSD / CC-BY only** — no non-commercial terms, no
revenue caps, no EU exclusions. Allowed: TripoSR (MIT), InstantMesh (Apache-2.0), TRELLIS
(MIT), SAM 3D Objects (commercial-OK), Depth Anything V2 Small (Apache-2.0), ABO (CC-BY-4.0),
OR-Tools (Apache-2.0), xeokit (MIT), IfcOpenShell, FAISS. Rejected: Hunyuan3D-2 (EU excluded),
Stable Fast 3D ($1M cap), Wonder3D (CC-BY-NC), YOLOv8/Ultralytics (AGPL).

**Cost (production).** Licence royalties: **$0, forever**. Infrastructure: a single hosted
GPU (Hetzner GEX44, Heilbronn) at **≈€185/month**, GDPR-clean, with marginal cost driven
**below $0.005 per room** at scale (retrieval covers most items; only a few need fresh
generation; OR-Tools runs on CPU; a self-hosted LLM removes per-call API cost).

## 9. Discussion and future work

- **Past the single-view ceiling:** the route to *metric* accuracy is **multi-view**
  (3–5 photos / photogrammetry) plus **absolute-scale calibration**, not a better single-image
  model. These are the next milestones.
- **IFC fidelity rides on detection + dimensions, not mesh quality** — so the BIM goal is more
  tractable than perfect geometry: correct object class + correct real-world size suffice for a
  valid, useful IFC schedule, with retrieval supplying clean geometry.
- **Open items:** per-item catalogue browsing over all 400 meshes; photo→retrieval wired into
  the app; the 4-way cloud bake-off; a desktop build.

## 10. Conclusion

The original project proved an end-to-end pipeline could be built; the original *premise* —
single-view reconstruction → BIM-grade IFC — was unsound. Acting on that, we built a working
**retrieval-and-layout** system that produces functional, exportable room models from a real
catalogue, and we replaced the "single-view is limited" assertion with a **reproducible
measurement** of that limit. The engineering infrastructure (web frontend, processing bridge,
IFC export, 3D viewer) was repurposed into a corrected architecture, and the accuracy harness
gives the project — and the paper — empirical ground to stand on.

---

## Appendix A — Figure index and reproducibility

All figures are server-side renders, regenerated from the pipeline by:

```
python backend/python-scripts/make_paper_figures.py     # fig00–fig08 + figures.tex
python backend/python-scripts/eval_photo3d.py --category office_chair --n 3   # accuracy data
python backend/python-scripts/make_accuracy_figure.py   # fig09
python backend/python-scripts/make_results_plate.py     # results_plate
```

| Figure | File |
|--------|------|
| Overview | figures/fig00_overview.png |
| Single workstation | figures/fig01_office_single_montage.png |
| Team office | figures/fig02_office_team_montage.png |
| Obstacles + door | figures/fig03_office_obstacles_montage.png |
| ADA | figures/fig04_office_ada_montage.png |
| Living room | figures/fig05_living_room_montage.png |
| Dense workspace | figures/fig06_workspace_dense_montage.png |
| Overpacked (infeasible) | figures/fig07_office_overpacked_montage.png |
| Capacity sweep | figures/fig08_capacity_sweep.png |
| Photo→3D accuracy | figures/fig09_accuracy_triposr.png |
| Composite plate | figures/results_plate.png |

## Appendix B — Source documents folded into this paper

papers/Research_Paper_3D_to_IFC_Critical_Analysis.md (May 2026 critical analysis);
docs/ACCURACY_RESULTS.md; docs/FINDINGS.md; docs/COST_MODEL.md; docs/PAPER_ASSETS.md.
Full source code and history: GitHub branch `app-development`.
