# Comparative Analysis

**Project:** 3DpicToIFCModeling (SCS) — photograph → 3D reconstruction → IFC/BIM export
**Chapter status:** Studies A and B complete; Study C (A100 pod extension) in flight — its result
tables are pre-formatted below with cells marked **PENDING**.
**Date:** 2026-07-11

This chapter consolidates every quantitative comparison the project has produced into one place:
the methodology of each study, the full results tables, and their interpretation. Every number in
this chapter is taken from a repository document; the source file is cited beneath each table.
Where a value was never measured or never written down, the cell reads *not recorded*.

---

## 1. Scope and Methodology

The project ran three quantitative studies. They answer three different questions and must not be
conflated:

| Study | Question | Inputs | Ground truth | Metric | Hardware | Status |
|---|---|---|---|---|---|---|
| **A** — 5-AI accuracy benchmark | Which single-image→3D generator is geometrically most accurate, and how do all of them compare to a real catalog mesh? | 10 furniture types, **one single front-view image each** | Real ABO/catalog meshes (scored 1.000 by definition) | Chamfer distance + F-score@0.02 after ICP alignment | RunPod H200 (143 GB); TripoSR baseline on local RTX 4050 (6.4 GB) | ✅ Complete (2026-06-30 → 07-01) |
| **B** — 170-item repair-pack A/B | Do the archetype repair packs improve TripoSR's shipped output (and the exported IFC) across all 17 app categories, on photos the pipeline has never seen? | 170 internet photos (10 lists × 17 categories), CLIP-validated, never from the catalog | None (internet photos) — reference is the photo itself | Silhouette IoU (best of 8 azimuths), mesh statistics (faces, components, watertightness), IFC4 export validation | RTX 4050 Laptop 6 GB (local) | ✅ Complete (2026-07-11) |
| **C** — A100 pod extension | How do the still-untested generators (TRELLIS.2-4B, Stable Fast 3D) score on the identical Study-A protocol, and how does every generator's output behave inside the actual app pipeline — on both the 10 Study-A inputs and the 170 Study-B photos? | Same 10 Study-A inputs **plus** the same 170 Study-B internet photos (plus a 5-item "wild" robustness track) | Same ABO ground truths for the 10; none for the 170 | Same scorer as Study A for the 10; visual gallery + app-pipeline repair/IFC report for the 170 | RunPod A100 80 GB (preferred) | ⏳ **PENDING** — pod run in flight |

Sources: `deliverable/CLOUD_BENCHMARK_FINDINGS.md`, `benchmark/README.md`,
`deliverable/cloud_bundle/RUNBOOK_REMAINING.md`.

### 1.1 Study A methodology (H200 5-AI accuracy benchmark)

- **Inputs.** 10 furniture types — bed, bookshelf, cabinet, chair, desk, lamp, office_chair, sofa,
  stool, table — each represented by **one single front-view 2D image**. The item list, source IDs
  (ABO product IDs and named catalog meshes such as `GothicBed_01`), input images, and ground-truth
  meshes are pinned in `deliverable/cloud_bundle/manifest.json`.
- **Ground truth.** The real ABO/catalog mesh for each item. Because the reconstruction is compared
  back to the *known* original, the catalog mesh scores 1.000 by definition and serves as the upper
  bound.
- **Scorer** (`deliverable/cloud_bundle/eval_accuracy.py`, identical for every model): both meshes
  are centred at the origin and scaled so the bounding-box diagonal equals 1; the reconstruction is
  then ICP-aligned to the ground truth (12 coarse seed rotations — 3 axes × 4 angles — each refined
  by up to 30 ICP iterations, best kept); 50,000 surface points are sampled per mesh with a fixed
  random seed for reproducibility. Reported metrics: **Chamfer distance** (mean bidirectional
  nearest-neighbour distance, lower is better) and **F-score @ τ = 0.02** in normalised units
  (harmonic mean of precision/recall of points within τ of the other surface, higher is better).
- **Generation seed 42** for every model (see the run commands in `deliverable/manuals/SAM3D.md`,
  `deliverable/manuals/TRELLIS.md`, and `deliverable/cloud_bundle/run_cloud_benchmark.py` usage in
  `deliverable/cloud_bundle/RUNBOOK_REMAINING.md`).
- **Models under test:** TripoSG (VAST-AI, MIT), SAM 3D Objects (Meta, SAM License),
  TRELLIS-image-large (Microsoft, MIT), InstantMesh (TencentARC, Apache-2.0), and the project's local
  baseline TripoSR (Stability, MIT) in two segmentation variants (rembg and SAM2 cutouts).
- **Hardware caveat (stated in the source):** TripoSR ran on the local RTX 4050 (6.4 GB); the four
  cloud generators ran on the H200 — cross-row *runtime* comparisons are therefore indicative, not
  strict. Accuracy comparisons are unaffected (same inputs, same scorer).

Source: `deliverable/CLOUD_BENCHMARK_FINDINGS.md`, `deliverable/cloud_bundle/eval_accuracy.py`.

### 1.2 Study B methodology (170-item TripoSR repair-pack A/B)

- **Question.** A/B proof that the archetype repair packs
  (`backend/python-scripts/repair_packs.py`) improve the mesh TripoSR ships today — and the quality
  of the exported IFC — for **all 17 furniture categories** in the app's picker, without changing
  the app.
- **Inputs.** 10 gallery "lists" × 17 categories = **170 unique internet photos**, never taken from
  the catalog, each CLIP-screened for semantic validity (subject present; not a room, painting, or
  person) and timestamped. Photo provenance (URL, source, fetch time) is recorded in
  `benchmark/images/sources.json`.
- **Per item:** one photo → the mesh TripoSR ships today (raw) → the same mesh after the repair
  pack (improved). Outputs per item: `raw.glb`, `improved.glb`, renders, `metrics.json`, and for
  spot-proofs an `item.ifc` exported by the app's own exporter (`saveIFC.py`).
- **Metrics.**
  - *Silhouette IoU vs the photo cutout*: because the photo's viewpoint is unknown, the mesh
    silhouette is rendered at **8 azimuths (0°–315°, step 45°)** and the best IoU against the
    normalised photo mask is kept (`benchmark/batch_generate.py`, `silhouette_iou`).
  - *Mesh statistics*: face count, component count, watertightness (a multi-part mesh counts as
    watertight only when **every** component is closed).
  - *IFC validation*: spot-proof exports through the app's real `saveIFC.py`, re-validated as IFC4.
- **Campaign:** 2026-07-11 05:13 → 08:00 local, **170/170 generated, 0 failures**, RTX 4050 Laptop
  6 GB, TripoSR loaded once, ~55 s/item.

Source: `benchmark/README.md`, `benchmark/batch_generate.py`,
`benchmark/results/list01..list10/summary.json`.

### 1.3 Study C methodology (A100 pod extension — PENDING)

The in-flight pod run (`deliverable/cloud_bundle/RUNBOOK_REMAINING.md`) extends Study A and bridges
it to Study B:

1. **Models:** TRELLIS.2-4B (first run), Stable Fast 3D (first run; licence-capped to
   benchmark-only use), SAM 3D Objects (re-run), TripoSG (re-verify).
2. **Track 1 — accuracy:** the SAME 10 single front-view images, ground truths, scorer
   (`score_all.py` → Chamfer + F@0.02, ICP) and seed 42 as Study A, so the new scores drop directly
   into the Study-A table.
3. **Track 2 — app-pipeline:** each generator's output is pushed through the app's actual repair +
   IFC4 export path (`app_pipeline_test.py` → `apptest/report.csv`) — "what works and what doesn't
   inside the product".
4. **Track 3 — the 170 internet photos:** `make_bench170_manifest.py` rebuilds the exact Study-B
   manifest (10 lists × 17 categories, same committed photos), so each pod model's mesh drops
   straight into the Study-B gallery/visualizer as a labelled candidate. No ground truth exists for
   these photos, so this track is **not** scored with `score_all.py`; the comparison is visual
   (gallery/visualizer winner selection) plus the app-pipeline repair/IFC report.
5. **Bonus track:** a 5-item "wild" robustness manifest (`wild_manifest.json`, no ground truth).
6. Stable Fast 3D additionally gets a raw-photo vs pre-segmented-cutout A/B (`--out out_seg`).

Completion criteria (the runbook's shutdown checklist): `cloud_scores.csv` rows present for every
model × 10 items, and `apptest/report.csv` present. Estimated cost: ~4 h ≈ $3–8.

Source: `deliverable/cloud_bundle/RUNBOOK_REMAINING.md`,
`deliverable/cloud_bundle/make_bench170_manifest.py`, `deliverable/cloud_bundle/wild_manifest.json`.

### 1.4 How the candidate set was chosen (selection funnel)

The five models in Study A (and the two added in Study C) are the survivors of a documented
six-stage funnel (`docs/HUGGINGFACE_MODEL_NARROWING.md`):

1. **Stage 1 (2026-04-29):** raw sweep of the HuggingFace `image-to-3d` tag ranked by
   trending/likes/downloads (the raw pool size was the live tag listing at sweep time and was not
   recorded — only the source URL, ranking method, and survivors are documented).
2. **Stage 2 (2026-06-06):** strict commercial-licence + hardware funnel → 10 cross-pipeline + 10
   detection candidates (`MODEL_SURVEY_SCS.md`, `deliverable/docs/TECHNICAL_REPORT_SCS.md` §6).
   Five inclusion criteria (verifiable licence, commercial grant SCS can meet, fits the 8 GB dev box
   natively or via offload, addresses a pipeline task) and four exclusion rules (AGPL/GPL, CC-BY-NC,
   research-only, model cards that disclaim deployment in body text — the OpenAI CLIP trap). Killed
   at this stage: Hunyuan3D-2 (EU/UK/S-Korea exclusion + 1M-MAU cap + output-binding clause),
   Stable Fast 3D as a production candidate (revenue cap — retained for benchmarking only),
   Wonder3D, Depth Anything V2 Base/Large, YOLOv8, OpenAI CLIP as a deployed model.
3. **Stage 3:** adoption of the retrieval-first production spine (DINOv2-Large + ABO catalog,
   SAM 2.1, Depth Anything V2 **Small**, TripoSR as generative fallback).
4. **Stage 4:** the measured 5-AI bake-off — **Study A of this chapter**.
5. **Stage 5:** still-untested candidates — **Study C of this chapter** (TRELLIS.2-4B, Stable Fast
   3D); Hunyuan3D-2 remains permanently untested because its licence excludes EU territory, making
   even a local benchmark run a violation risk.
6. **Stage 6:** the post-generator quality layer — **Study B of this chapter**.

---

## 2. Study A Results — H200 5-AI Accuracy Benchmark

### 2.1 Overall ranking (mean F-score@0.02 over the 10 items)

| Model | Type | Licence | Mean F@0.02 | Notes |
|---|---|---|---|---|
| **ABO mesh (ground truth)** | real catalog mesh | CC-BY-4.0 (attribution) | **1.000** | upper bound by definition |
| **TripoSG** (VAST-AI) | rectified-flow SDF | MIT | **0.393** | best generator; spiky (stool 0.99, table 0.10) |
| **SAM 3D Objects** (Meta) | flow-matching MoT (geometry+texture+pose) | SAM License | **0.368** | 2nd overall; wins cabinet 0.73; weak planar desk 0.05; native pose output |
| **TRELLIS-image-large** (Microsoft) | SLAT flow | MIT | **0.347** | mesh-only export; great stool 0.99 / bed 0.67, weak bookshelf 0.16 / table 0.18 |
| **InstantMesh** (TencentARC) | Zero123++ → sparse-view LRM | Apache-2.0 | **0.328** | wins the flat table (0.81) where TripoSG/TRELLIS fail |
| **TripoSR · rembg** (local baseline) | triplane LRM | MIT | 0.295 | |
| **TripoSR · SAM2** (local baseline) | triplane LRM | MIT | 0.278 | |

Ranking: **TripoSG > SAM 3D > TRELLIS > InstantMesh > TripoSR.**
The primary result: **the real ABO mesh (1.000) beats the best generator (TripoSG 0.393) ~2.5×** —
all three newer flow models beat the older TripoSR LRM, but none approach the real mesh,
reinforcing the project's *detect → retrieve → parametric* recommendation over generation for BIM.

Source: `deliverable/CLOUD_BENCHMARK_FINDINGS.md` (results table and "Primary result holds"
paragraph); confirmed in `deliverable/manuals/README.md` status board.

### 2.2 Full score matrix — F-score@0.02 per model per furniture type

Per-item scores from the benchmark's score file (best generator per row in **bold**; the TripoSR
columns are the local baselines):

| Item | TripoSG | SAM 3D | TRELLIS | InstantMesh | TripoSR·rembg | TripoSR·SAM2 |
|---|---|---|---|---|---|---|
| bed | 0.285 | 0.370 | **0.672** | 0.172 | 0.431 | 0.209 |
| bookshelf | **0.752** | 0.151 | 0.155 | 0.156 | 0.550 | 0.181 |
| cabinet | 0.538 | **0.725** | 0.483 | 0.416 | 0.026 | 0.197 |
| chair | 0.197 | **0.232** | 0.231 | 0.221 | 0.222 | 0.272 |
| desk | 0.086 | 0.046 | **0.126** | 0.089 | 0.094 | 0.130 |
| lamp | 0.206 | 0.176 | 0.171 | **0.326** | 0.230 | 0.336 |
| office_chair | 0.604 | **0.628** | 0.292 | 0.392 | 0.394 | 0.496 |
| sofa | 0.173 | **0.250** | 0.172 | 0.102 | 0.000 | 0.334 |
| stool | **0.993** | 0.895 | 0.991 | 0.587 | 0.477 | 0.328 |
| table | 0.095 | 0.206 | 0.179 | **0.814** | 0.531 | 0.298 |
| **Mean** | **0.393** | **0.368** | **0.347** | **0.327**¹ | **0.295** | **0.278** |

¹ The per-item mean computed from the score file is 0.3274; the findings document reports the
InstantMesh mean as 0.328. Both are shown for transparency.

Source: `deliverable/cloud_gallery/cloud_scores.csv` (per-item values; means computed from the
per-item rows), `deliverable/CLOUD_BENCHMARK_FINDINGS.md` (reported means).

### 2.3 Full score matrix — Chamfer distance (lower is better)

| Item | TripoSG | SAM 3D | TRELLIS | InstantMesh | TripoSR·rembg | TripoSR·SAM2 |
|---|---|---|---|---|---|---|
| bed | 0.1717 | 0.0963 | **0.0367** | 0.1838 | 0.1292 | 0.1550 |
| bookshelf | **0.0332** | 0.2024 | 0.2031 | 0.2001 | 0.0471 | 0.1858 |
| cabinet | 0.0343 | **0.0300** | 0.0478 | 0.0758 | 0.2556 | 0.2214 |
| chair | 0.1649 | 0.1488 | 0.1597 | **0.1480** | 0.1779 | 0.1500 |
| desk | 0.2760 | 0.2926 | **0.2674** | 0.2739 | 0.2373 | 0.3472 |
| lamp | 0.1996 | 0.1982 | 0.1975 | **0.1382** | 0.1943 | 0.1812 |
| office_chair | 0.0375 | **0.0374** | 0.1212 | 0.1088 | 0.1007 | 0.0561 |
| sofa | 0.1719 | **0.1326** | 0.1698 | 0.2038 | 0.3423 | 0.1165 |
| stool | 0.0151 | 0.0181 | **0.0097** | 0.0386 | 0.0593 | 0.0760 |
| table | 0.1805 | 0.1105 | 0.0981 | **0.0282** | 0.0421 | 0.1973 |
| **Mean²** | 0.128 | 0.127 | 0.131 | 0.140 | 0.159 | 0.169 |

² Mean Chamfer per model is not separately recorded in the findings document; the means above are
computed from the per-item rows of the score file. Note that by mean Chamfer, SAM 3D edges out
TripoSG — the two headline metrics agree on the top tier but order it differently, another reason
the project reports F@0.02 as primary and Chamfer as corroboration.

Source: `deliverable/cloud_gallery/cloud_scores.csv`.

### 2.4 Per-shape complementarity — which model wins which furniture type

The central qualitative finding of Study A: **no single generator dominates per item.**

Counting per-item winners among the four cloud generators (from the F@0.02 matrix above):

| Winner | Items won | Item(s) and score |
|---|---|---|
| **SAM 3D** | 4 | cabinet 0.725, office_chair 0.628, sofa 0.250, chair 0.232 |
| **TripoSG** | 2 | stool 0.993, bookshelf 0.752 |
| **TRELLIS** | 2 | bed 0.672, desk 0.126 |
| **InstantMesh** | 2 | table 0.814, lamp 0.326 |

Interpretation (as stated in the findings document):

- **TripoSG/TRELLIS win on compact upholstered forms** (stool ~0.99) but **collapse on flat planar
  furniture** (table ~0.10).
- **InstantMesh is the opposite** — its Zero123++ multiview stage reconstructs the **flat table at
  0.81 (8× TripoSG)** yet trails on the compact pieces.
- **SAM 3D wins the boxy cabinet (0.73)** — best of all generators on that class — and is top-tier
  on office_chair (0.63) / stool (0.89), but, like TripoSG, collapses on the flat desk (0.05).
- This suggests a **router** (pick the generator by predicted shape class) would beat any single
  model — but all still sit far below the real mesh.

The complementarity was demonstrated concretely: the **best-of-each 10-item IFC4 catalog** built by
`cloud/build_ifc_catalog.py` (each item sourced from its highest-scoring model, decimated to 8 k
faces, Z-up, scaled to real-world metres — a 2.4 MB IFC4 file that loads in Revit/ArchiCAD) drew
its winners from **four different models** (TripoSG ×2, SAM 3D ×4, TRELLIS ×2, InstantMesh ×2).
The strongest deployable catalog is a *router*, not any single model.

An honest additional observation derivable from the score file: on 4 of the 10 items (chair, desk,
lamp, sofa) the local **TripoSR·SAM2 baseline out-scored every cloud generator** (0.272 / 0.130 /
0.336 / 0.334) — the cloud models' aggregate advantage is carried by large wins on a subset of
shapes, not uniform superiority.

Source: `deliverable/CLOUD_BENCHMARK_FINDINGS.md` (complementarity paragraph, Finding B
"Demonstrated population"), `deliverable/cloud_gallery/cloud_scores.csv` (per-item winners).

### 2.5 Runtime and VRAM comparison

Wall-clock per furniture item, measured from the inference logs:

| Model | GPU | Avg | Min | Max | Note |
|---|---|---|---|---|---|
| TripoSR | RTX 4050 (local, 6.4 GB) | ~15 s | ~12 s | ~26 s | feed-forward core is <0.5 s on an A100; the rest is 256³ marching cubes + post-processing |
| TripoSG | H200 | **10.6 s** | 7.4 s | 16.0 s | rectified-flow SDF, 50 steps |
| SAM 3D | H200 | **8.7 s** | 6.3 s | 16.5 s | **fastest measured**; sdpa attention backend; geometry+texture+pose in one pass |
| TRELLIS | H200 | **19.4 s** | 9.3 s | 33.9 s | first call adds ~15 s nvdiffrast JIT compile; 50-step flow + mesh decode |
| InstantMesh | H200 | ~10 s | not recorded | not recorded | Zero123++ → sparse-view LRM |
| TRELLIS.2-4B | *not yet run* | ~17 s @1024³ | 3 s @512³ | 60 s @1536³ | per HF model card, on H100 — PENDING measurement in Study C |

Caveat from the source: TripoSR ran on the local 6.4 GB GPU, the rest on the H200 — not the same
hardware, so cross-rows are indicative. Reading: all generators run in **~7–35 s/image** on a
datacenter GPU — fine for offline/batch catalog building, too slow for real-time. Speed is not the
deciding factor; the ~2.5× quality gap to the real mesh is.

VRAM requirements as documented in the per-model manuals:

| Model | VRAM floor (as documented) | Source |
|---|---|---|
| TripoSR | ~4 GB @ 256³ marching cubes (runs on the 6 GB RTX 4050 Laptop) | `MODEL_SURVEY_SCS.md` §5; `benchmark/README.md` |
| TripoSG | ≥8 GB | `deliverable/manuals/TripoSG.md` |
| SAM 3D Objects | ≥32 GB (manual requirement); community estimates ~24 GB at native precision — model card states no minimum | `deliverable/manuals/SAM3D.md`; `MODEL_SURVEY_SCS.md` §6 |
| TRELLIS-image-large | ≥16 GB | `deliverable/manuals/TRELLIS.md` |
| InstantMesh | not recorded (an earlier 8 GB local attempt needed a degraded "collapsed-cube" workaround; ran native on the H200) | `deliverable/manuals/InstantMesh.md` |
| TRELLIS.2-4B | ≥24 GB, CUDA ≥12.4 | `deliverable/manuals/TRELLIS2.md` |
| Stable Fast 3D | ~7 GB est. | `MODEL_SURVEY_SCS.md` §5 |

### 2.6 Methodological findings that qualify Study A

Three findings from the benchmark are methodological, not model rankings, and matter for anyone
reproducing or reviewing the numbers (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`):

- **Finding A — inconsistent mesh orientation.** Single-image→3D models output meshes in different
  canonical orientations, and even the ABO ground-truth catalog is not consistently oriented
  (measured "tallest axis" per mesh differs per model and per item — e.g. office_chair: ABO GT = Y,
  TripoSG = Z, TripoSR·SAM2 = X). Consequence: a naive fixed-camera gallery presents faulty,
  non-comparable views. The scorer is immune (ICP with 12 seed rotations), but the visual galleries
  required per-mesh orientation normalisation, content-cropped re-padded framing, and one fixed
  front-facing camera orbit for every model.
- **Finding B — outputs are IFC4-valid but impractically high-poly.** TripoSG meshes export to
  valid IFC4 (`IfcTriangulatedFaceSet`, correct entity classes, spatial hierarchy) but run 1–2 M
  faces (a 3-object scene → a 138 MB IFC file). SAM 3D is the worst offender: raw marching-cubes
  output of 130 k – 1.06 M faces (sofa = 1,056,860; office_chair = 794,200). For practical
  Revit/BIM use every generator's output must be decimated (≈ ≤8 k faces): "BIM-compliant: yes,
  after decimation." A second caveat: automatic Z-up + height-to-metres normalisation lands most
  items correctly but fails where height is not the defining dimension (a generated bed came out
  0.70×0.74×0.55 m).
- **Finding C — deployment is the real barrier, not the models.** Getting each model to produce a
  single `.glb` took 5–9 distinct dependency fixes (SAM 3D alone: 12 — see §4). Licensing flag:
  TRELLIS and InstantMesh require `nvdiffrast` (NVIDIA Source Code License) — research-use OK,
  commercial flag.

---

## 3. Study B Results — 170-Item TripoSR Repair-Pack A/B

### 3.1 Campaign record

| Fact | Value |
|---|---|
| Items | 170 (10 lists × 17 app categories), one internet photo each, all CLIP-validated |
| Generated | **170/170, 0 failures** |
| Campaign window | 2026-07-11 05:13 → 08:00 local (list01 started 05:13:52, list10 finished 08:00:09 — total wall ~2 h 46 min³) |
| Hardware | RTX 4050 Laptop 6 GB (local) |
| Throughput | TripoSR loaded once, ~55 s/item |
| Per-list outcome | every list: 17 ok, 0 failed |

³ Total wall time derived from the first/last timestamps in
`benchmark/results/list01/summary.json` and `benchmark/results/list10/summary.json`; each of the
10 per-list summaries records 17 ok / 0 failed.

Source: `benchmark/README.md`, `benchmark/results/list01..list10/summary.json`.

### 3.2 Headline A/B outcomes (170 items)

| Metric | TripoSR today (raw) | After repair packs |
|---|---|---|
| Mean faces | 111,143 | **12,039 (9.2× lighter)** |
| Watertight solids | fragments individually closed | **91% fully closed objects** |
| Broken bases rebuilt | shipped broken | **48** (evidence-driven: legs at detected stub positions / tripod / trestle / pedestal / plinth) |
| Silhouette IoU vs photo | 0.662 | 0.646 (shape preserved while restructuring) |
| IFC spot-proofs | — | **20/20 valid IFC4** with real mesh geometry (`saveIFC.py`, the app's exporter) |

Interpretation: the repair layer removes ~89% of the face budget, closes 91% of objects into
watertight solids, and rebuilds 48 structurally broken bases — while the silhouette IoU moves only
0.662 → 0.646, i.e. the restructuring **preserves the photographed shape** (a 0.016 IoU cost for a
9.2× lighter, watertight, IFC-exportable mesh). Every IFC spot-proof passed through the app's real
exporter validated as IFC4.

Source: `benchmark/README.md` (headline table and honest notes).

### 3.3 Per-archetype behaviour

Every CLIP label / picker category resolves to one of **7 repair archetypes**; each runs a
hand-picked stack of 8 guarded CPU stages (a failing stage falls back):

| Archetype | Categories | Signature fixes |
|---|---|---|
| legged | table, desk, coffee/side table, stool, chair, bench | strict symmetry; support health check → evidence-driven rebuild |
| swivel_seat | office_chair | drift removal + the proven 5-star base graft |
| boxy | cabinet, filing_cabinet, bookshelf, wardrobe, dresser | crisp-edge smoothing, plinth rebuild |
| upholstered | sofa, couch, armchair, bed | Taubin×14 fabric softness, plinth |
| panel | mirror, picture_frame, clock, monitor, tv | tanh thickness clamp — flat wall slabs |
| slender | lamp, planter, plant | thin-part-protecting filters, no forced symmetry |
| prop | laptop + anything unknown | safe universal clean (the fallback for any object) |

Universal stages (in order): up-aware debris filter (keeps legs/poles) → per-component pymeshfix →
detected-plane symmetry snap (axis+offset chamfer-scored — no X=0 assumption) → Taubin smooth →
decimate to 10–15 k → panel flatten → final crumb-sweep + watertight heal → support rebuild (only
when the bottom is broken; an intact tripod/pedestal always passes the health check) → flush floor
contact.

Qualitative per-archetype outcome (as recorded): where the photo is a clean single object the
improvement is obvious (office chairs, stools, clocks, cabinets). A per-archetype *quantitative*
breakdown of the headline metrics was not recorded as an aggregate — per-item numbers live in each
item's `metrics.json` under `benchmark/results/`.

Source: `benchmark/README.md`.

### 3.4 Known limitations (recorded honestly in the source)

- **Angled/cluttered museum-style shots** produce blobby bodies — the repair fixes their
  *structure* (solid, grounded, light, IFC-valid) but cannot invent detail the single view never
  contained.
- **Known v3 candidates:** gentle auto-level for tilted items; sofa blockiness.
- **CLIP on flat single-colour renders is unreliable** (calls everything a stool) — kept per-row as
  an honest "render reads as" note, excluded from the headline metrics.

### 3.5 Defects surfaced by the benchmark (already fixed)

The A/B campaign doubled as a stress test of the repair layer and found real bugs, all fixed:

1. **Axis swap in support building** — legs built in local Z-up then rotated landed 90° off in
   plan; the builder now works directly in world coordinates.
2. **Decimation opens cracks; the support cut opens the body** — a final `_finalize` stage (crumb
   sweep + fill_holes + per-component pymeshfix) restores watertightness.
3. **Internet photos need semantic screening** — CLIP validation of every photo, with curated
   Wikimedia `Category:` listings as the refill source for sparse types.
4. **Wikimedia throttles bulk full-res downloads** — use `iiurlwidth=1024` thumbnail URLs.

Source: `benchmark/README.md` (engineering notes).

---

## 4. Cost–Benefit Analysis — One Decision Table

Consolidated from the accuracy study, the runtime logs, the licence survey, and the per-model
deployment manuals ("install fixes" = distinct error→fix entries documented in each manual):

| Model | Licence (+ flags) | VRAM floor | Install effort (documented fixes) | Speed (s/item, measured) | Mean F@0.02 | Deployment verdict (from the manuals) |
|---|---|---|---|---|---|---|
| **TripoSR** | MIT | ~4 GB @256³ (runs on 6 GB laptop GPU) | already integrated in the app | ~15 (local RTX 4050); ~55 s/item full Study-B pipeline | 0.278–0.295 | The only engine that runs on the 6 GB consumer box; no compiled rendering deps |
| **TripoSG** | MIT; **no nvdiffrast** | ≥8 GB | **5** ("easiest of the cloud models") | 10.6 (H200) | **0.393** | Cleanest commercially of the cloud set; quality spiky (great compact forms, poor flat planes) |
| **SAM 3D Objects** | SAM License (royalty-free, no MAU/revenue cap, no geo exclusion); training dataset SA-3DAO is CC-BY-NC → most legal attention; gated weights | ≥32 GB (manual); ~24 GB community est. | **12** (hardest deploy; solved via the sdpa attention backend) | **8.7 (H200, fastest measured)** | 0.368 | Uniquely outputs pose (scale/rotation/translation); highest-poly output of all — decimation mandatory |
| **TRELLIS-image-large** | MIT, but **requires nvdiffrast (NVIDIA Source Code License — commercial flag)** | ≥16 GB | **9** ("hardest install of the set" among the first four) | 19.4 (H200) | 0.347 | Mesh-only export used (texture bake needs another compiled ext); honor pinned commits |
| **InstantMesh** | Apache-2.0, but requires nvdiffrast (same flag); Zero123++ dependency provenance flagged in the technical report | not recorded (8 GB needed a degraded workaround locally; native on H200) | not recorded (manual not updated post-run; findings doc: 5–9 fixes per model) | ~10 (H200) | 0.328 | Wins flat/planar furniture outright; stochastic multiview stage |
| **TRELLIS.2-4B** | MIT (same compiled-extension family) | ≥24 GB | PENDING (Study C) | ~17 @1024³ (HF card, H100) — PENDING | PENDING | Newest, full PBR; separate repo/package (`trellis2` + `o_voxel`) |
| **Stable Fast 3D** | Stability Community License — free only < US$1M annual revenue → **benchmark-only** for SCS | ~7 GB est. | PENDING (Study C) | PENDING | PENDING | Only surveyed model that explicitly emits PBR materials |

Sources: `deliverable/manuals/README.md` (status board), `deliverable/manuals/TripoSG.md`,
`deliverable/manuals/SAM3D.md`, `deliverable/manuals/TRELLIS.md`,
`deliverable/manuals/InstantMesh.md`, `deliverable/manuals/TRELLIS2.md`,
`deliverable/CLOUD_BENCHMARK_FINDINGS.md`, `MODEL_SURVEY_SCS.md`,
`deliverable/docs/TECHNICAL_REPORT_SCS.md` §6, `docs/HUGGINGFACE_MODEL_NARROWING.md`.

### 4.1 Why TripoSR remains the local default

On the project's actual deployment hardware — a 6 GB consumer GPU (RTX 4050 Laptop) — TripoSR is
the **only** generator in the table that runs at all: TripoSG needs ≥8 GB, TRELLIS ≥16 GB,
TRELLIS.2 ≥24 GB, SAM 3D ≥32 GB per its manual, and InstantMesh required a degraded workaround at
8 GB. It is MIT-licensed with no compiled rendering dependency, already integrated end-to-end in
the app, and proven at scale by Study B: 170/170 internet photos, zero failures, ~55 s/item on the
6 GB laptop. Its raw accuracy deficit (0.278–0.295 vs 0.393) is partially compensated *behind* it
by the generator-agnostic repair layer (Study B), which fixes exactly the failure class Study A
exposed — fragmented, over-dense, structurally broken meshes — at zero GPU cost.

### 4.2 How the bigger engines slot in on capable hardware

- **TripoSG (≥8 GB, MIT, no nvdiffrast)** is the natural first upgrade: the best measured accuracy,
  the cleanest commercial position of the cloud set, and the lowest install effort (5 fixes).
- **SAM 3D (≥24–32 GB)** is the pick where a workstation-class GPU exists and object *pose* matters
  — it is the fastest measured, second-most accurate, and the only engine emitting
  scale/rotation/translation natively (directly useful for room placement); its custom licence and
  NC dataset need the most legal attention.
- **TRELLIS / InstantMesh** carry the nvdiffrast commercial flag and are therefore benchmark
  references rather than deployment candidates in the current licence posture.
- Because the repair packs are generator-agnostic (Study B; and Study C's `app_pipeline_test.py`
  runs them over every pod model's output), any of these engines drops into the same
  repair → IFC4 path without app changes. The Study-A complementarity result means the ideal
  "capable hardware" configuration is a **shape-class router** across engines, not a single
  replacement (see §6).

---

## 5. Study C — A100 Pod Extension (PENDING)

The tables below are pre-formatted to the exact shape of the pod run's outputs
(`out/cloud_scores.csv`, `apptest/report.csv` — see `deliverable/cloud_bundle/RUNBOOK_REMAINING.md`).
Cells will be filled when the run completes; until then every value is **PENDING**.

### 5.1 Accuracy — same 10 inputs, same ground truths, same scorer, seed 42 (F-score@0.02)

| Item | TRELLIS.2-4B | Stable Fast 3D | SAM 3D (re-run) | TripoSG (re-verify) |
|---|---|---|---|---|
| bed | PENDING | PENDING | PENDING | PENDING |
| bookshelf | PENDING | PENDING | PENDING | PENDING |
| cabinet | PENDING | PENDING | PENDING | PENDING |
| chair | PENDING | PENDING | PENDING | PENDING |
| desk | PENDING | PENDING | PENDING | PENDING |
| lamp | PENDING | PENDING | PENDING | PENDING |
| office_chair | PENDING | PENDING | PENDING | PENDING |
| sofa | PENDING | PENDING | PENDING | PENDING |
| stool | PENDING | PENDING | PENDING | PENDING |
| table | PENDING | PENDING | PENDING | PENDING |
| **Mean F@0.02** | PENDING | PENDING | PENDING (Study A: 0.368) | PENDING (Study A: 0.393) |

Acceptance gate (runbook checklist): `cloud_scores.csv` rows present for every model × 10 items.
The SAM 3D and TripoSG columns are consistency re-runs — material deviation from the Study-A means
would indicate an environment or seed problem, not a model change.

### 5.2 Chamfer distance (same protocol; lower is better)

| Item | TRELLIS.2-4B | Stable Fast 3D | SAM 3D (re-run) | TripoSG (re-verify) |
|---|---|---|---|---|
| bed … table (10 rows) | PENDING | PENDING | PENDING | PENDING |
| **Mean** | PENDING | PENDING | PENDING | PENDING |

### 5.3 Runtime per image (from the pod inference logs)

| Model | GPU | Avg | Min | Max |
|---|---|---|---|---|
| TRELLIS.2-4B | A100 80 GB | PENDING | PENDING | PENDING |
| Stable Fast 3D | A100 80 GB | PENDING | PENDING | PENDING |
| SAM 3D (re-run) | A100 80 GB | PENDING | PENDING | PENDING |
| TripoSG (re-verify) | A100 80 GB | PENDING | PENDING | PENDING |

Reference expectation for TRELLIS.2-4B from its HF model card (H100): ~17 s @1024³, 3 s @512³,
60 s @1536³ (`deliverable/CLOUD_BENCHMARK_FINDINGS.md` compute-time table).

### 5.4 App-pipeline test — repair + real IFC4 export per model (`apptest/report.csv`)

| Model | Items repaired OK | Faces raw → repaired | Watertight after repair | Valid IFC4 exports | Notes |
|---|---|---|---|---|---|
| TRELLIS.2-4B | PENDING | PENDING | PENDING | PENDING | PENDING |
| Stable Fast 3D | PENDING | PENDING | PENDING | PENDING | PENDING |
| SAM 3D | PENDING | PENDING | PENDING | PENDING | PENDING |
| TripoSG | PENDING | PENDING | PENDING | PENDING | PENDING |

### 5.5 Stable Fast 3D segmentation A/B (raw photo vs pre-segmented cutout)

| Variant | Mean F@0.02 | Mean Chamfer |
|---|---|---|
| SF3D (raw photo, own rembg) | PENDING | PENDING |
| SF3D (pre-segmented cutout, `out_seg`) | PENDING | PENDING |

### 5.6 The 170-photo extension (no ground truth — visual + app-pipeline)

Each pod model's meshes for the 170 Study-B photos (`make_bench170_manifest.py` rebuilds the
identical 10-list × 17-category manifest) drop into the Study-B visualizer
(`benchmark/visualizer.html`) as labelled candidates alongside TripoSR raw and repaired. This
track is deliberately **not** scored with the Chamfer/F-score harness (no ground truth exists for
internet photos); the deliverables are:

| Output | Content | Status |
|---|---|---|
| Visualizer candidate wins (`selections.json`) | Per-item winner across {TripoSR raw, TripoSR repaired, each pod model} chosen in the side-by-side 3D visualizer | PENDING |
| Per-category win counts by model | Aggregated from `selections.json` | PENDING |
| Wild robustness track (5 items, `wild_manifest.json`) | Qualitative behaviour on uncontrolled photos | PENDING |

Sources for §5: `deliverable/cloud_bundle/RUNBOOK_REMAINING.md`,
`deliverable/cloud_bundle/make_bench170_manifest.py`,
`deliverable/cloud_bundle/wild_manifest.json`, `benchmark/README.md` (visualizer workflow).

---

## 6. Conclusions

1. **Retrieval-first is validated quantitatively.** The real ABO catalog mesh scores 1.000 by
   construction; the best of five measured generators (TripoSG) reaches 0.393 mean F@0.02 on the
   identical inputs and scorer — a ~2.5× gap. The three newer flow models (TripoSG 0.393, SAM 3D
   0.368, TRELLIS 0.347) all beat the older TripoSR LRM (0.278/0.295), but none approach the real
   mesh. For BIM — where colour, material, metric dimensions, and determinism all matter — the
   project's *detect → retrieve → parametric* spine remains the correct primary path; generation is
   the fallback for out-of-catalog items. (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`)

2. **The repair packs are a generator-agnostic quality layer, proven at scale.** Study B shows the
   post-processing layer converts what TripoSR ships today into BIM-ready assets on 170/170 unseen
   internet photos with zero failures: 9.2× lighter (111,143 → 12,039 mean faces), 91% watertight,
   48 evidence-driven base rebuilds, 20/20 valid IFC4 spot-proofs — at a silhouette-IoU cost of
   only 0.662 → 0.646. Because the layer keys off shape archetypes, not off TripoSR, it applies
   behind ANY engine in this chapter; Study C's app-pipeline track tests exactly that.
   (`benchmark/README.md`, `docs/HUGGINGFACE_MODEL_NARROWING.md` Stage 6)

3. **A shape-class router is the highest-value future work on the generative side.** No single
   generator dominates per item: SAM 3D wins boxy volumes (cabinet 0.725), TripoSG/TRELLIS win
   compact forms (stool 0.99) but collapse on flat planes (table ~0.10), and InstantMesh inverts
   that (table 0.814). The best-of-each IFC4 catalog draws from four different models. A router
   that predicts the shape class and dispatches to the best engine would beat every single model
   measured — while still sitting far below the retrieval path, which the router therefore
   complements rather than replaces. (`deliverable/CLOUD_BENCHMARK_FINDINGS.md`)

4. **Deployment cost, not model quality, is the practical differentiator among generators.**
   Every cloud engine needed 5–12 documented dependency fixes to produce its first `.glb`; two of
   the four carry an NVIDIA-licensed compiled renderer that flags them commercially; the hardware
   floor spans 4 GB → 32 GB. On the project's 6 GB consumer target, TripoSR + repair packs is the
   only viable local configuration today; TripoSG is the cleanest upgrade at ≥8 GB; SAM 3D is the
   choice at ≥24–32 GB when pose output justifies its legal review. (`deliverable/manuals/README.md`)

5. **Open items.** Study C fills the two deliberate gaps in the accuracy table (TRELLIS.2-4B,
   Stable Fast 3D), re-verifies two Study-A results on new hardware, and extends the comparison
   from the 10 controlled inputs to the 170 uncontrolled photos through the app's own
   repair-and-export path. Its tables in §5 are pre-formatted for direct drop-in.

---

## Appendix: Source Documents for Every Number in This Chapter

| Document | Contributes |
|---|---|
| `deliverable/CLOUD_BENCHMARK_FINDINGS.md` | Study A design, ranking, runtimes, Findings A/B/C, best-of-each catalog |
| `deliverable/cloud_gallery/cloud_scores.csv` | Study A per-item F-score and Chamfer values (§2.2, §2.3) |
| `deliverable/cloud_bundle/eval_accuracy.py` | Scorer definition (normalisation, ICP seeding, sampling, τ) |
| `deliverable/cloud_bundle/manifest.json` | The 10 Study-A items, source IDs, inputs, ground truths |
| `deliverable/manuals/README.md` + `TripoSG.md`, `SAM3D.md`, `TRELLIS.md`, `InstantMesh.md`, `TRELLIS2.md` | VRAM floors, install-fix counts, deployment verdicts |
| `benchmark/README.md` | Study B design, headline metrics, archetypes, limitations, engineering notes |
| `benchmark/batch_generate.py` | Silhouette-IoU (best-of-8-azimuths) and watertightness definitions |
| `benchmark/results/list01..list10/summary.json` | Study B per-list execution record and campaign wall time |
| `deliverable/cloud_bundle/RUNBOOK_REMAINING.md` + `make_bench170_manifest.py` + `wild_manifest.json` | Study C scope, protocol, acceptance gates |
| `MODEL_SURVEY_SCS.md` | Licence verbatims, VRAM estimates, candidate roles |
| `deliverable/docs/TECHNICAL_REPORT_SCS.md` §6 | Survey methodology, licence taxonomy, InstantMesh/Hunyuan3D flags |
| `docs/HUGGINGFACE_MODEL_NARROWING.md` | The six-stage selection funnel (§1.4) |
