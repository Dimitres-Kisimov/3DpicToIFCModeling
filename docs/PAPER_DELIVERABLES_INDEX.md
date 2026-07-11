# Final Paper — Deliverables Index

**Updated:** 2026-07-11 (evening). One page mapping every paper asset to where it
lives in the repository. Items marked ⏳ are being produced by the running pod
campaign and land in the same locations.

## 1. Core documents (paper chapters map)

| Paper section | Source document | State |
|---|---|---|
| System overview & architecture | [PROJECT_DOCUMENTATION_FINAL.md](PROJECT_DOCUMENTATION_FINAL.md) · [CODEBASE_MAP.md](CODEBASE_MAP.md) | ✅ |
| Model selection methodology (7k → funnel) | [HUGGINGFACE_MODEL_NARROWING.md](HUGGINGFACE_MODEL_NARROWING.md) — Stages 1–8 | ✅ |
| Comparative studies (A/B/C/D) | [COMPARATIVE_ANALYSIS.md](COMPARATIVE_ANALYSIS.md) | A,B ✅ · C ⏳ pod · D planned |
| Multi-image reconstruction (Mode 2) | [MULTI_IMAGE_RESEARCH.md](MULTI_IMAGE_RESEARCH.md) — incl. Study E protocol | ✅ research; run ⏳ |
| **Security & Compliance (dedicated section)** | [SECURITY_COMPLIANCE.md](SECURITY_COMPLIANCE.md) | ✅ |
| Cost analysis | [COST_MODEL.md](COST_MODEL.md) | ✅ |
| Accuracy deep-dive | [ACCURACY_RESULTS.md](ACCURACY_RESULTS.md) · `deliverable/CLOUD_BENCHMARK_FINDINGS.md` | ✅ |
| IFC optimization algorithms | [IFC_OPTIMIZER.md](IFC_OPTIMIZER.md) | ✅ |
| Per-engine deployment manuals (12 AIs) | `deliverable/manuals/` (proven: TripoSG/SAM3D/TRELLIS/InstantMesh/TripoSR; draft: Direct3D-S2, Step1X-3D, Hi3DGen, PartCrafter, MIDI-3D, Unique3D) | ✅ |

## 2. Figures & graphics (paper-ready, 200 dpi)

| Figure | File | Data source |
|---|---|---|
| Study A: 5-AI accuracy vs catalog reference | `docs/figures/fig_study_a_fscores.png` | H200 run, CLOUD_BENCHMARK_FINDINGS |
| Study B: repair packs IoU before→after, 17 categories | `docs/figures/fig_study_b_repair_iou.png` (+ `study_b_category_means.csv` for the table) | live aggregate of `benchmark/results/*/metrics.json` (170 items) |
| Regenerate / extend | `benchmark/make_paper_figures.py` — reruns from current data; Study C/E figures will be added here after the pod campaign | — |

## 3. Interactive visualizations (screenshots for the paper come from these)

| Page | URL (serve `benchmark/` on :8000) | Shows |
|---|---|---|
| A/B gallery hub, lists 01–11 | `http://localhost:8000/index.html` | photo vs raw vs repaired renders + stats |
| Candidate visualizer | `http://localhost:8000/visualizer.html` | side-by-side spinning 3D, **comparison groups** (vs OURS / vs TripoSG / multi-image / all), per-AI amber emblems, ↻90°/⤴90° rotate, winner selection & export |
| Research hub (whole-project comparisons) | app `:3000` Research tab | all 15 historical comparison pages |
| Manuals in-app | app `:3000` Manuals page | all 12 engine manuals incl. next-wave drafts |

## 4. Tangible test evidence

| Evidence | Location | State |
|---|---|---|
| 187 benchmark photos + full provenance (URL/source/timestamp) | `benchmark/images/` + `images/sources.json` | ✅ (10 lists + list11 grand-comparison list) |
| 170-item TripoSR raw/improved meshes + renders + metrics | `benchmark/results/list01..10/` | ✅ |
| list11 all-AI grand comparison | `benchmark/results/list11/` + pod `out170/<engine>/list11_*` | ⏳ |
| Research-10 meshes per engine (identical inputs, seed 42) | pod `out/<engine>/` → Research tab after download | ⏳ queue3 |
| **Per-AI IFC folders** (compliant exports only) | `benchmark/ifc/<engine>/` (created by `ingest_pod_results.py`) | ⏳ after pod download |
| App-pipeline compatibility report (repair+IFC per engine × item) | pod `apptest/report.csv` | ⏳ queue3 |
| Accuracy scores CSV (Chamfer + F@0.02) | pod `out/cloud_scores.csv` → Study C tables | ⏳ queue3 |
| Catalog with engine-badged generated items | `data/generated_assets/manifest.json` (`engine` field drives picker badge) | ✅ mechanism · ⏳ pod items |
| Six-campaign system test report | repo (2026-07-09 commit `bdb10cf`) | ✅ |

## 5. Comparisons pipeline (how a new engine's results become paper assets)

```
pod results tarball
  └─ python benchmark/ingest_pod_results.py <extracted>
       ├─ benchmark/results/listNN/<cat>/<engine>.glb   → visualizer candidates (auto-labelled emblem)
       ├─ IFC4 gate (repair → saveIFC → validate)       → benchmark/ifc/<engine>/*.ifc
       ├─ data/generated_assets/ + manifest engine tag  → app catalog badges
       └─ benchmark/ingest_report.csv                   → paper compliance table
```

## 6. Known result-integrity notes (report honestly in the paper)

- Study B shows the repair packs **trade a few IoU points in 5 categories**
  (table, side_table, stool, office_chair, desk) for the 9× face reduction and
  IFC-clean geometry — silhouette fidelity is not the optimization target;
  BIM-validity is. State this; it preempts the obvious reviewer question.
- The 2026-07-11 fabrication incident (placeholder meshes logged as OK) and the
  controls it produced (preflight gates, identical-output postcheck, no-fallback
  scripts) belong in the Security & Compliance section — they are a
  result-integrity contribution.
- One deterministic failure: mirror photos can defeat foreground extraction
  (`list08_mirror`); visible as an honest gap in the gallery.
