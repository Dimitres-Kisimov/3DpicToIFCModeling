# From Photograph to BIM: A Commercial-Safe Pipeline for Single-Image Furniture Reconstruction, IFC Export, and Room Synthesis — and an Empirical Case Against Single-View Generation

**A technical research monograph of the SCS *3DpicToIFCModeling* project**

**Author:** Dimitres Kisimov (SCS) · engineering, experiments, and drafting conducted with AI assistance (Claude Code)
**Date:** 30 June 2026
**Repository:** `3DpicToIFCModeling`, branch `app-development`
**Status of artifacts:** all code, data, benchmarks, figures, and this document are version-controlled and pushed (commits `540757f`, `540bbdd`, `58e6838`).

---

## Abstract

We present the full design, implementation, and empirical evaluation of a commercial-safe pipeline
that converts a single photograph of office furniture into a classified, metrically-dimensioned
IFC/BIM element, and arranges such elements into ergonomically valid room layouts. The work spans
roughly three months and many branches; this monograph consolidates it, including the directions
that **failed**. Our central empirical contribution is a controlled **150-model benchmark across six
conditions and three datasets** (Amazon Berkeley Objects, the CC0 Poly Haven library, and a research
Objaverse subset) demonstrating that **single-view neural 3D generation is structurally inadequate
for furniture**: the real ground-truth mesh outperforms the best generated mesh by 2–6× in F-score
in *every* condition. We document a critical, previously-undiagnosed defect — an unconditional
state-dictionary remap that loaded 192 image-encoder weights as random values under `transformers`
5.5.4, silently corrupting every reconstruction for twenty days — and its proof and fix. We survey
**eight** generative approaches that were attempted (TripoSR, SAM 3D Objects, TRELLIS, InstantMesh,
Stable Fast 3D, Hunyuan3D-2, the Meshy cloud API, and depth-mesh heightfields) and the reasons each
failed: an ill-posed single-view ceiling, an 8 GB shared-VRAM hardware wall, a Windows/Python
toolchain that lacks wheels for the heavy CUDA extensions, commercial-licensing exclusions, and a
hard determinism requirement. We then describe the resulting pivot to a **detection-plus-retrieval**
architecture (DETR + Depth-Anything-V2 + DINOv2/FAISS over a commercial-safe catalog), its IFC4
export and CP-SAT room-layout engine, and a cost model establishing a near-zero marginal cost at a
**$0 licence-royalty** posture. We conclude with an evidence-based recommendation — *detect → retrieve
→ parametric primitive*, never generation — and a roadmap. Throughout, we treat the failures as
first-class results: an account of what does *not* work, and precisely why, is the most reusable
output of this project.

**Keywords:** single-view 3D reconstruction, building information modeling, IFC, image segmentation,
object detection, mesh retrieval, Chamfer distance, F-score, commercial licensing, reproducibility,
negative results, TripoSR, SAM 2, DINOv2, ABO, Poly Haven, Objaverse.

---

## Contents

1. Introduction
2. Background and Related Work
3. System Architecture and Design Constraints
4. Generative 3D Reconstruction: A Survey of Attempts and Failures
5. The TripoSR Integration and Its Adaptation Journey
6. Methodology of the Controlled Benchmark
7. Results
8. Detection and Retrieval: The Alternative Path
9. The Pivot: From Generation to Retrieval
10. IFC/BIM Export and Room Synthesis
11. Cost Model and Commercial Viability
12. Discussion
13. Threats to Validity
14. Limitations and Future Work
15. Conclusion
— Acknowledgements · References · Appendices A–E

---

## 1. Introduction

*[To be written: the photo→IFC vision, the BIM motivation, why single-image capture is attractive
and why it is hard, the project's evolution across phases, and an enumerated statement of
contributions. Draws on the project-history digest.]*

---

## 2. Background and Related Work

*[To be written: single-view LRMs (TripoSR), multi-view generative reconstruction (InstantMesh,
TRELLIS, SAM 3D), salient-object vs promptable segmentation (U²-Net/rembg vs SAM 2), object
detection (DETR), monocular metric depth (Depth-Anything-V2), self-supervised features and retrieval
(DINOv2, FAISS), the IFC4 standard, the ABO/Poly Haven/Objaverse datasets, and reconstruction
metrics (Chamfer, F-score). Draws on the model-survey and technical digests.]*

---

## 3. System Architecture and Design Constraints

*[To be written: the end-to-end pipeline; the three hard constraints — commercial-safe licensing
only, 6.4 GB local / capped-cloud GPU, BIM-grade IFC goal; the local-only privacy posture; the
two parallel paths (generation vs detection+retrieval). Draws on the technical digest.]*

---

## 4. Generative 3D Reconstruction: A Survey of Attempts and Failures

This section is the project's most reusable negative result: a catalogue of every neural 3D-generation
approach that was attempted, and the specific, reproducible reason each one failed to meet the
project's needs. Eight distinct approaches were tried over three months and several branches. None
became the production path; the strongest reached only "last-resort fallback." We organise the survey
by approach, and close with six cross-cutting failure themes that, together, motivate the pivot of §9.

A structural caution for the reader, established during this survey: on the shipping branch, two of
these approaches — *InstantMesh* and *Stable Fast 3D* — never actually ran the model whose name they
bear. Their adapter scripts were first hardcoded placeholder cubes and later relabeled depth-mesh
heightfields. Real implementations existed only on side branches or in an unrun cloud bake-off. We
flag this explicitly to avoid the trap of mistaking a label for a capability.

### 4.1 TripoSR (Stability AI) — the only generator that shipped, kept as a degraded fallback

**Approach.** TripoSR is a single-view Large Reconstruction Model: a transformer encoder over image
patches predicts a triplane, from which a continuous density field is sampled and meshed by marching
cubes. It is feed-forward and deterministic, ~0.5 B parameters, ~1.3 GB of weights, trained on
~800,000 Objaverse objects. Its licence is **MIT** — commercially safe — which is why, despite its
quality ceiling, it survived as the production fallback.

**Integration.** TripoSR was wired end-to-end from Phase 1 (`backend/python-scripts/run_triposr.py`),
meshing at 256³ on the GPU. Its adaptation is documented as fourteen "Changes" (§5); the relevant
*failures* are summarised there, including the Python-3.14 marching-cubes port, three failed colour
schemes, a reverted topology-editing experiment, and the critical weight-load regression that is the
subject of §5.4 and §7.1.

**Measured quality ceiling.** An early accuracy harness (`docs/ACCURACY_RESULTS.md`) scored three ABO
office chairs (ABO mesh as ground truth; Chamfer + F-score@τ=0.02 with multi-seed ICP) at mean
Chamfer **0.169**, F-score **0.155**, precision ≈ 0.81, **recall ≈ 0.09**. The interpretation recorded
at the time is decisive: TripoSR "recovers only ~9 % of the true surface — it cannot see the back or
sides of the object from one photo," and a single-view reconstruction of the *correct* chair scores
about the same on coverage as a *wrong* chair — "usable for client visualisation, not BIM-grade
geometry." Generation took ~105 s (≈670 k faces) on the 6.4 GB RTX 4050 in one run, ~23–26 s in
others. Our later 150-model benchmark (§6–§7) confirms and generalises this ceiling.

**Verdict.** The model survey's final word: "Last-resort fallback only … it cannot address SCS's
failure modes — no PBR, no metric scale, asymmetric output, no determinism. Keep it as the last-resort
fallback … but do not invest more in it." It nonetheless became the de facto production generator
because it "ships consistently every time, takes ~23 seconds, and never risks the display driver" —
the only generator for which that was true.

### 4.2 TRELLIS-image-large (Microsoft) — installed, ran, architecturally non-functional on the hardware

**Approach.** TRELLIS is a Structured-Latent (SLAT) diffusion model that decouples sparse 3D geometry
from dense local features (~2 B parameters; the same architectural family as Meta's SAM 3D). Its
licence is **MIT** — commercially safe.

**Integration — the most-engineered attempt in the project.** TRELLIS is Linux-only; its custom CUDA
extensions (`diffoctreerast`, `mipgaussian`, `nvdiffrast`, `kaolin`, `spconv-cu`) have no Windows
wheels and fail to source-build on Windows. The team therefore built an entire **WSL2 (Ubuntu 22.04)
subsystem with GPU passthrough** (`/dev/dxg`), bridged from Windows by subprocess
(`WSL_TRELLIS_SETUP.md`, ~480 lines; branch `feat/trellis-wsl-fallback`). The verified environment
required a non-obvious MKL downgrade — "the 2025.0 → 2023.1 downgrade was needed because PyTorch 2.4.0
links against `iJIT_NotifyEvent` which mkl ≥ 2024.1 no longer exports" — alongside PyTorch 2.4.0/CUDA
11.8, xformers 0.0.27, spconv 2.3.8, kaolin 0.18.0, and ~3 GB of weights. The adapter
(`run_trellis_wsl.py`) capped PyTorch at 6 GB of the 8 GB VRAM, used the xformers attention backend,
and reduced sampling to 25 steps.

**Failure — a seven-test catalogue (Appendix A of the setup doc, 2026-06-14).** Every configuration
failed; the conclusion was that "TRELLIS-image-large is non-functional on this hardware class …
Microsoft's effective minimum is ≥ 16 GB of *dedicated* VRAM." Representative failures: OOM at the
spconv mesh-extraction stage ("954 MiB free when spconv tried 98 MiB chunk"); a PyTorch-2.4 internal
assert that `expandable_segments` is incompatible with `set_per_process_memory_fraction()`; repeated
OOM at `slat_decoder_mesh`; and — most alarming — a **display-driver TDR** when offloading 3 GB of
weights out of VRAM tripped the Windows 2-second watchdog, killing the WSL distro with no log flush
("one step short of a display freeze or BSOD"). A full-CPU fallback was impossible because the
attention path hard-imports `xformers.ops.memory_efficient_attention`, which has no CPU kernel.

**Verdict.** Abandoned to a disabled fallback. Commit `9adaacd` ("park TRELLIS for ≥16 GB hardware")
flipped its enable flag from 1 to 0; the cascade now falls through silently to TripoSR. Re-enablement
requires a discrete ≥16 GB card that does not also drive the display.

### 4.3 SAM 3D Objects (Meta) — the strongest candidate on paper; blocked by `pytorch3d` on Windows

**Approach.** Meta's pose-aware single-image-to-3D model (released 2025-11-19) emits geometry, 6-DoF
pose, and texture, deterministically (~3 B parameters). Its **SAM Licence** was audited as
commercial-safe: a "non-exclusive, worldwide, non-transferable and royalty-free limited license"
restricted only against ITAR/military/weapons/espionage uses — no revenue cap, no MAU cap, no
geographic exclusion. The survey ranked it #2 overall and "the strongest fallback for items missing
from the catalog."

**Integration (branch `sam3d-integration-wip`, `SAM3D_SETUP.md`).** Substantial progress, but
inference never ran. HuggingFace gated access was granted; **13.82 GB of weights** were downloaded
(`ss_generator.ckpt` 6.4 GB, `slat_generator.ckpt` 4.7 GB, plus decoder and encoders). A *separate
Python 3.12 interpreter* was required (the main pipeline is 3.13) because kaolin and open3d lack 3.13
Windows support. A `_kaolin_stub.py` was written to work around a kaolin DLL-load failure on
torch 2.12+cu126.

**Failure — the blocker.** `pytorch3d` has no Windows wheel for Python 3.12 + torch 2.12; the inference
pipeline imports `look_at_view_transform` and `Transform3d` from it, and the smoke test fails with
`ModuleNotFoundError: No module named 'pytorch3d'`. A Windows source build is "~30 min compile, ~50 %
success rate" per community reports. A secondary VRAM concern (24–32 GB native) meant it "belongs on a
capped-paid cloud GPU" regardless.

**Verdict.** Paused, not killed. It was wired into the planned cloud bake-off (`compare_4way.sh`,
`stage_sam3d`) to run on a RunPod A40; those results are not in the repository. The
`sam3d-primary-pivot` branch preserves the integration.

### 4.4 InstantMesh (TencentARC) — three implementations, none working locally

InstantMesh has the most tangled history in the project: **three distinct "InstantMesh" code paths**
existed, and none produced a working real-InstantMesh mesh on local hardware. The model itself is a
two-stage method — Zero123++ multi-view diffusion synthesises six views, then a sparse-view LRM
(FlexiCubes geometry) reconstructs a textured mesh; **Apache-2.0**, non-deterministic.

- **(A) Placeholder cube (Phase 3, `544a72f`).** The original `run_instantmesh.py` returned a hardcoded
  minimal GLB cube with fixed "2048 vertices / 4096 faces"; the comment reads "This is a placeholder
  implementation."
- **(B) Relabeled depth-mesh (current branch).** Today's `run_instantmesh.py` does not run InstantMesh
  at all — it calls `generate_segmented_depth_mesh(...)` with Depth-Anything-V2-Small, i.e. a 2.5-D
  heightfield of the masked foreground. The name is a label only.
- **(C) Real InstantMesh in WSL (`cc56866`, 2026-06-16).** A genuine attempt: Zero123++ (seed 42) →
  InstantMesh `instant-mesh-base` with a *monkey-patched chunked SDF/deformation MLP* to fit
  FlexiCubes in 8 GB. Install required pinning transformers 4.40.0 / diffusers 0.27.2 /
  huggingface_hub 0.23.0 and shipping a local `zero123plus.py` (the historical `custom_pipeline`
  string had been removed from diffusers). **Result:** "11 smoke tests confirmed the chunked-MLP path
  produces collapsed-SDF cubes" — reducing `grid_res` below the trained 128 makes the SDF MLP emit
  all-positive values, triggering InstantMesh's "Step 3 fallback" that returns a default cube.

**Verdict.** Abandoned locally (cubes); deferred to the cloud bake-off, where it is rated reliable on a
48 GB A40. No local quality numbers were ever obtained.

### 4.5 Stable Fast 3D (Stability AI) — never really integrated; licence-capped

**Approach.** A single-image-to-3D model notable for explicitly emitting **PBR materials**
(albedo/roughness/metalness) with a delighting step (~1.1 B params, ~7 GB).

**Integration.** Like InstantMesh, only fake forms existed: a Phase-3 placeholder, then a relabeled
depth mesh (`generate_segmented_depth_mesh(..., "Intel/dpt-hybrid-midas")`). The real model was never
installed.

**Failure — licence.** Stability's Community Licence is "free for non-commercial use, as well as for
commercial use by organizations or individuals with less than US$1,000,000 in annual revenue." The
project's rejected list records "Stable Fast 3D ($1M cap)"; it is commercially unsafe unless SCS
confirms it sits below the cap.

**Verdict.** Rejected on licence; never a real implementation.

### 4.6 Hunyuan3D-2 (Tencent) — real adapter written, rejected on a "triple-AVOID" licence

**Approach.** Texture-baked multi-view diffusion (shape pipeline + paint pipeline producing UV-mapped
PBR meshes), non-deterministic. A real adapter (`run_hunyuan3d.py`) was written in Sprint 7 (branch
`Original-TripoSR`, `93c2a94`): rembg → shape diffusion (30 steps, guidance 5.0) → texture bake.

**Failure — licence (three independent blockers).** The Tencent Community Licence (i) "DOES NOT APPLY
IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA" — fatal to an EU/UK deployment; (ii) is revoked
above 1,000,000 MAU; and (iii) forbids using outputs "to improve any other AI model" — which would
block feeding generated meshes back into the retrieval index. The rejected list records "Hunyuan3D-2
(EU excluded)."

**Verdict.** Rejected purely on licence; weights never downloaded.

### 4.7 Meshy cloud API — adapter written, rejected on the local-only/privacy posture

**Approach.** A managed cloud image-to-3D API (`run_meshy_api.py`): POST a base64 image to
`api.meshy.ai`, poll up to ten minutes, download the GLB. The only "generator" here that is a hosted
service rather than local weights.

**Failure — architecture/policy, not capability.** It violates the project's foundational local-only
constraint: "no managed-API call to an external service during a customer-facing operation, and no
transmission of customer photographs out of the SCS network." The technical report's explicit
objections are vendor lock-in and licensing opacity ("the model behind it may be under unknown
terms").

**Verdict.** Effectively dead code; never appears in the survey, cascade, or cost model.

### 4.8 Depth-mesh heightfields — the real engine behind the "fake" generators

**Approach.** Not a generative model: `generate_segmented_depth_mesh` performs foreground segmentation
(originally AGPL YOLOv8, replaced by rembg/U²-Net, later SAM 2) → monocular depth (Intel DPT or
Depth-Anything-V2) → a coloured mesh of the masked pixels only. It is a single-view 2.5-D relief with
no back or sides — structurally weaker than even TripoSR — and survives only as the implementation
masquerading under the InstantMesh and Stable Fast 3D names (§4.4B, §4.5).

### 4.9 Wonder3D — rejected at survey on licence; never integrated

A single-image multi-view-diffusion method, rejected at the survey stage as **CC-BY-NC**
(non-commercial). No code was written.

### 4.10 Cross-cutting failure themes

Six themes recur across the survey and motivate the pivot of §9:

1. **The single-view problem is ill-posed, universally.** The four failure modes — asymmetry,
   hallucinated hidden surfaces, non-determinism, and absent PBR/metric scale — "persist across every
   model in the 2026 state of the art … They are not bugs in TripoSR specifically; they are properties
   of the *class* of approach." Quantified by our benchmark (§7) and the early ~9 % surface recall.
2. **An 8 GB shared-display VRAM wall** killed every heavy generator locally: TRELLIS OOM/TDR, SAM 3D's
   24–32 GB need, InstantMesh's collapsed-cube under chunked MLP.
3. **A Windows/Python wheel-availability wall** blocked SAM 3D (`pytorch3d`), TRELLIS (Linux-only CUDA
   extensions → forced WSL2), TripoSR (`torchmcubes` on 3.14), and kaolin (DLL load on torch 2.12).
4. **Commercial-licensing gating** eliminated capable models: Hunyuan3D-2 (EU/UK + MAU + no-output-reuse),
   Stable Fast 3D ($1M cap), Wonder3D (CC-BY-NC), YOLOv8 (AGPL), Depth-Anything Base/Large (CC-BY-NC).
   Only MIT/Apache/BSD/SAM-Licence survived.
5. **A determinism requirement** (the same chair must yield the same mesh in every room) structurally
   rules out all diffusion generators as the *primary* path.
6. **A fake/placeholder lineage** meant "InstantMesh" and "Stable Fast 3D" never ran on the shipping
   branch — a cautionary tale about labels versus capabilities.

Together these explain why, after exhausting the generative state of the art, the project pivoted to
detection-plus-retrieval (§9).

---

## 5. The TripoSR Integration and Its Adaptation Journey

*[To be written from `TripoSR_CHANGES_AND_LESSONS.md`: the fourteen Changes in narrative form — the
marching-cubes port (Change 1), GPU/CUDA migration (Change 2), background removal (Change 3),
resolution (Change 4), component filtering (Change 5), the three colour schemes (Change 6), smoothing
(Change 7), orientation (Change 8), the reverted symmetry experiment (Change 9), SAM 2 + k-means
(Change 10), the metric-scale fixes (Change 11), the UTF-8 IFC fix (Change 12), Lens2BIM (Change 13),
and the critical weight-load defect (Change 14). Emphasise the corrections and reverts.]*

---

## 6. Methodology of the Controlled Benchmark

*[To be written: the six-condition, three-dataset design; Chamfer/F-score@0.02 with ICP; the
SCS_TRIPOSR_SEGMENTER A/B; the apparatus; the datasets and their licences; the bias-removal logic.
Mirrors PAPER_Single_View_Furniture_3D §3–§4.4 but at monograph depth.]*

---

## 7. Results

*[To be written: §7.1 the weight-load root-cause and proof (Table: raw vs remapped key matching);
§7.2 qualitative real-photo behaviour (figures); §7.3 the 150-model six-condition scoreboard; §7.4
robustness and the input-conditioned segmenter finding. Imports the figures and tables already in the
paper/report.]*

---

## 8. Detection and Retrieval: The Alternative Path

*[To be written from the project-history digest: DETR detection and the office-furniture detection
benchmark; CLIP classification (and its weakness); DINOv2 + FAISS retrieval over ABO; the catalog
construction (downloader, 400→515); the FAISS index desync (400 vs 515); the photo-vs-silhouette
domain gap; parametric primitives.]*

---

## 9. The Pivot: From Generation to Retrieval

*[To be written: the strategic turn, the evidence that drove it, and why retrieval+parametric beats
generation for BIM. Draws on PIVOT_BLUEPRINT and the survey.]*

---

## 10. IFC/BIM Export and Room Synthesis

*[To be written from the technical digest: IFC4 export (IfcOpenShell, entity types, property sets,
spatial hierarchy); the CP-SAT room-layout engine (OR-Tools, rule packs, Neufert/ADA ergonomics,
wall-affinity, seat-facing); the ephemeral-until-export web app.]*

---

## 11. Cost Model and Commercial Viability

*[To be written from the cost-model digest: the $0 licence-royalty posture; infrastructure costs;
Heilbronn/Hetzner EUR figures; per-room marginal cost; the self-hosting argument.]*

---

## 12. Discussion
## 13. Threats to Validity
## 14. Limitations and Future Work
## 15. Conclusion

*[To be written.]*

---

## Acknowledgements · References · Appendices

*[References (extensive) and Appendices A (reproducibility/artifacts), B (full per-model scores),
C (the fourteen-change lessons log), D (figure gallery + spinning-mesh stills), E (branch/experiment
evolution timeline) — to be written.]*
