# HuggingFace Model Narrowing — The Complete Funnel (index)

**Purpose:** one page that shows HOW the project went from "everything on
HuggingFace" to the hand-selected models in production and in the Research tab —
why each was chosen, and which were deliberately never tested. The four source
documents are linked at every stage; this page is the map.

## The funnel, stage by stage

### Stage 1 — Raw sweep of the HuggingFace image-to-3D tag (2026-04-29)
**Docs:** [TEAM_ROADMAP.md](../TEAM_ROADMAP.md) · [DEVELOPMENT_ROADMAP_PHASE2.md](../DEVELOPMENT_ROADMAP_PHASE2.md)
Source: `huggingface.co/models?pipeline_tag=image-to-3d&sort=trending` — the whole
tag, ranked by **trending / likes / monthly downloads**. Selections recorded with
their popularity numbers: TRELLIS (MIT, 600+ likes), InstantMesh (Apache-2.0,
14k+ downloads/mo), Hunyuan3D-2 (74k+ downloads/mo, 1,750 likes — the tag's most
downloaded, flagged for licence review), honorable mention Stable Fast 3D.

### Stage 2 — Strict commercial-licence + hardware funnel → 20 candidates (2026-06-06)
**Docs:** [MODEL_SURVEY_SCS.md](../MODEL_SURVEY_SCS.md) ·
[TECHNICAL_REPORT_SCS.md §6](../deliverable/docs/TECHNICAL_REPORT_SCS.md) ·
[OFFICE_FURNITURE_DETECTION_BENCHMARK.md](../deliverable/docs/OFFICE_FURNITURE_DETECTION_BENCHMARK.md)
Five inclusion criteria (verifiable licence on the model card → commercial grant
SCS can meet → fits the 8 GB dev box natively or via offload → addresses a pipeline
task) and four exclusion rules (AGPL/GPL · CC-BY-NC · research-only · model cards
that disclaim deployment in body text even with a permissive file licence — the
OpenAI CLIP trap). Every licence claim quoted verbatim from the model card.
**Output: 10 cross-pipeline + 10 detection candidates.**

**Killed here, with reasons (the "looks free, isn't" list):**
| Model | Why rejected |
|---|---|
| Hunyuan3D-2 | EU/UK/S-Korea territory exclusion + 1M-MAU cap + output-binding clause |
| Stable Fast 3D | Stability Community License — free only < US$1M revenue (benchmark-only) |
| Wonder3D | CC-BY-NC (non-commercial) |
| Depth Anything V2 Base/Large | CC-BY-NC — **only the Small variant is Apache-2.0** |
| YOLOv8 / Ultralytics | AGPL-3.0 viral |
| OpenAI CLIP (as deployed model) | model card: "any deployed use case … out of scope" |

### Stage 3 — Adopted into production (the retrieval-first spine)
**Doc:** [MODEL_SURVEY_SCS.md §8](../MODEL_SURVEY_SCS.md)
DINOv2-Large + ABO catalog (retrieval) · SAM 2.1 (segmentation) · Depth Anything V2
**Small** (metric scale) · TripoSR (generative fallback) · CLIP fine-tune
(classification). Rationale: the retrieval framing solves colour/material/
dimension/determinism at once — no generative model surveyed does.

### Stage 4 — The measured 5-AI bake-off (H200, 2026-06-30 → 07-01)
**Docs:** [CLOUD_BENCHMARK_FINDINGS.md](../deliverable/CLOUD_BENCHMARK_FINDINGS.md) ·
per-model deployment recipes in [manuals/](../deliverable/manuals/README.md) ·
visual galleries in the app's 🔬 Research tab.
Identical inputs (10 furniture types, ONE single front-view image each), identical
scorer (Chamfer + F@0.02, ICP, seed 42):
**TripoSG 0.393 > SAM 3D 0.368 > TRELLIS 0.347 > InstantMesh 0.328 > TripoSR 0.278–0.295**,
vs the real ABO mesh at 1.000 — the catalog beats the best generator ~2.5×,
confirming retrieval-first. Key finding: per-shape complementarity (TripoSG wins
stools, InstantMesh wins flat tables, SAM 3D wins cabinets) → a shape-class router
would beat any single model.

### Stage 5 — Still untested (and why)
| Model | Status |
|---|---|
| TRELLIS.2-4B | manual pre-written ([TRELLIS2.md](../deliverable/manuals/TRELLIS2.md)); needs ≥24 GB — next pod run |
| Stable Fast 3D | infer script ready; benchmark-only (licence cap) — next pod run |
| SAM 3 / SigLIP 2 / Grounding DINO | shortlisted; run locally, no pod needed |
| Detection finalists (OWLv2, Florence-2, OneFormer…) | benchmark script delivered; awaits a labelled SCS photo set |
| Hunyuan3D-2 | permanently untested — licence excludes EU territory; even a local benchmark run is a violation risk |

### Stage 6 — Post-generator quality layer (2026-07-11)
**Doc:** [benchmark/README.md](../benchmark/README.md)
Archetype repair packs proven on 170 internet photos (10 lists × 17 categories):
faces 111k→12k, 48 broken bases rebuilt evidence-driven, 91% watertight, 20/20
valid IFC4 spot-proofs — generator-agnostic, applies behind ANY engine above.

### Stage 7 — Second license audit: the 2025–26 wave (2026-07-11)
Every notable open-weights image-to-3D release since the Stage-2 funnel was
re-verified against the same rules (weights licence checked separately from code
licence, dependency licences traced).

**New USABLE candidates (royalty-free, EU-safe) — queued for a future pod run:**
| Model | Org | Licence (code / weights) | Notes |
|---|---|---|---|
| Direct3D-S2 | DreamTechAI | MIT / MIT | was already on the Stage-3 shortlist; high-res sparse-SDF geometry, 10–24 GB |
| Step1X-3D | StepFun | Apache-2.0 / Apache-2.0 | one of very few fully-permissive **textured** pipelines; 27–29 GB |
| Hi3DGen (Stable3DGen) | Stable-X | MIT / MIT + Apache-2.0 | TRELLIS-based, NVIDIA-NC deps explicitly removed by authors for commercial use |
| PartCrafter | PKU/CMU | MIT / MIT | part-level meshes (drawers/legs as parts) — interesting for furniture |
| DeepMesh | Tsinghua | Apache-2.0 / Apache-2.0 | remesh stage — the licence-clean replacement for MeshAnything |

**Newly confirmed BANNED (the "looks free, isn't" list grows):**
| Model | Trap |
|---|---|
| CraftsMan3D | README says MIT, but the HF **weights** are tagged AGPL-3.0 — the artifact you download controls |
| Era3D | AGPL-3.0 (and multiview-only anyway) |
| PartPacker | NVIDIA Non-Commercial License |
| Kiss3DGen | Apache tag, but pipeline hard-requires FLUX.1-dev (Non-Commercial) — licence-washing |
| Amodal3R | weights CC-BY-4.0 but inference code S-Lab 1.0 NC — can't run one without the other |
| **MeshAnything / V2** | **S-Lab License 1.0 — non-commercial without written permission.** Listed in the Stage-2 survey CSV; never integrated into the pipeline. Do not integrate — use DeepMesh instead. |
| SPAR3D | SF3D's successor, same Stability revenue cap — benchmark-only |

---
*Note: the raw size of the Stage-1 pool was the live HuggingFace tag listing at
sweep time; the docs record the source URL, ranking method, and survivors — not
the raw count.*
