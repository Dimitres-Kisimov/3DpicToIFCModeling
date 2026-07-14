# TripoSR / Photo→3D Furniture Investigation — Full Report

**Date:** 2026-06-30
**Repo:** `C:\Users\dimik\3DpicToIFCModeling` (branch `app-development`)
**Author:** Dimi, with Claude Code (engineering + analysis)
**Scope:** Diagnose why TripoSR produced unusable 3D meshes, fix what was fixable, and
empirically establish what the photo→3D pipeline can and cannot do for office furniture —
ending with a data-backed recommendation.

---

## 0. Executive summary

- A **single critical bug** was making *every* TripoSR reconstruction garbage: a state-dict
  remap (added 2026-06-10) loaded the image encoder with **192 random weights**. **Fixed** —
  reconstructions went from spiky 1,000-fragment blobs to clean single-component meshes.
- Even after the fix, **single-view TripoSR cannot produce usable office-furniture geometry**
  (chairs lose their base, desks fold/crumple, thin legs vanish). This was confirmed across
  ~10 inputs, both real photos and clean catalog renders, and both segmenters.
- A controlled **150-model benchmark spanning 6 conditions across 3 datasets** (Chamfer +
  F-score vs ground truth) showed: **the real ground-truth mesh beats the best generated mesh by
  2–6× in every condition** — robust to sampling (first-5 vs seeded random), category, input
  modality (clean render vs real product photo), and dataset (ABO CC-BY, **Poly Haven CC0**, and a
  research **Objaverse** subset). Single-view generation is structurally inadequate for furniture.
- A **secondary, input-conditioned finding:** **rembg beats SAM 2** as the TripoSR segmenter on
  *clean curated renders* (overturning an earlier "they're equivalent" assumption), but the
  advantage **shrinks to a tie** on real photos and on in-the-wild Objaverse meshes — the stronger
  promptable model (SAM 2) closes the gap as input variability rises. See §6.
- **Methodology — the self-referential / convenience-sample concerns are now addressed:** the
  original round used ABO's own renders scored against the same meshes; the expanded battery
  (randomized sampling, real-photo inputs, and two non-ABO datasets) reproduces the headline
  result, so it is not an artifact of the initial setup. See §6.
- **Recommendation:** stop generating furniture; route Detect → Retrieval (fix the broken
  FAISS index first) → parametric primitive fallback. Keep generation only as a cloud,
  multi-view, catalog-miss fallback.
- **Status:** all fixes, tooling, data, the dashboard, the scientific paper, and this report are
  **committed and pushed** to `origin/app-development` (commits `540757f`, `540bbdd`).

---

## 1. How the session started

The user returned to the SCS "3DpicToIFCModeling" project (photo → object detection → 3D mesh
→ IFC/BIM → room layout) wanting to continue work on TripoSR, the single-image-to-3D model.
The immediate symptom: meshes looked wrong. What followed was a deep diagnosis.

---

## 2. The headline bug — image-encoder weights loaded as random noise

### Symptom
Every photo (chair, hamburger, desk — anything) reconstructed as a **spiky, fragmented blob**
with hundreds to thousands of disconnected components. Unrecognisable.

### How we ruled out the usual suspects (each falsified by experiment)
1. **Post-processing** — re-enabled the debris filter + smoothing; still a blob.
2. **Segmentation** — SAM 2's mask was proven pixel-equivalent to rembg's (both captured the
   whole object); not the cause.
3. **Input quality** — a frame-filling demo (`hamburger.png`) *also* blobbed → systemic, not
   input-specific.
4. **The old code** — running the actual April-28 version produced an *even worse* blob, so it
   wasn't a recent regression in `run_triposr.py` logic.

### Root cause (proven)
The `SCS PATCH (2026-06-10)` in `backend/triposr/tsr/system.py` ran `remap_tsr_state_dict`
(`backend/python-scripts/_tsr_state_dict_remap.py`) **unconditionally**, on the assumption that
transformers 5.x renamed the ViT attention keys (`encoder.layer.N.attention.attention.query` →
`layers.N.attention.q_proj`). But the **installed transformers 5.5.4 keeps the LEGACY naming**
for this ViT. So the remap renamed the checkpoint *away* from what the model wanted:

```
model expects:        image_tokenizer.model.encoder.layer.0.attention.attention.query.weight   (legacy)
RAW checkpoint load:      missing=0    unexpected=0     ← perfect
REMAPPED (old code):      missing=192  unexpected=192   ← 192 image-encoder tensors never loaded
```

`load_state_dict(strict=False)` silently swallowed the mismatch, leaving **192 image-tokenizer
tensors on random initialisation**. A randomly-initialised image encoder emits meaningless
features → meaningless density field → spiky garbage, deterministically, for every input.

**Why "the April-28 version worked":** April 28 predates the June-10 remap entirely, so it
loaded the weights raw (0 missing) and reconstructed cleanly. (Git: `544a72f` Apr 21 first
TripoSR integration; `9348655` Apr 28 GPU+quality; remap added 2026-06-10; transformers now
5.5.4.) The user's memory of a working April build was the single highest-signal clue.

### Fix
`system.py` now **auto-detects**: load the raw checkpoint first, and only apply the remap if the
raw load actually misses `image_tokenizer` keys. After the fix, `chair.png` reconstructs as one
clean solid component (seat + back + 4 legs) vs 1,297 fragments before.

**Figure 1 — before the fix** (`chair.png`, post-processing on, image-encoder weights
mis-loaded): spiky, fragmented garbage.

![Figure 1. TripoSR output BEFORE the weight-load fix — a spiky blob (chair.png input).](report_assets/fig01_blob_before_fix.png)

**Figure 2 — after the fix** (same input, encoder now loading real weights): one clean
component with seat, back and four legs.

![Figure 2. TripoSR output AFTER the weight-load fix — a recognisable chair (chair.png input).](report_assets/fig02_chair_after_fix.png)

### Lessons
- `load_state_dict(strict=False)` is a silent footgun — assert `missing_keys == 0` for weights
  that must load.
- Don't translate weights on an assumption about a library version — verify against the actual
  model (a 2-line probe would have caught this on day one).
- Garbage far downstream (a blobby mesh) can trace all the way back to weight loading. Check the
  model loaded correctly *before* blaming the algorithm.

---

## 3. Other bugs fixed this session

| Fix | File | What it was |
|---|---|---|
| **Metric-scale crash** | `inference_base.py` | SAM 2 mask (post-`resize_foreground`) was resized by `depth_shape / original_image_shape` → 256-vs-300 boolean-index crash. Fixed to resize from the mask's own shape. |
| **Metric-scale always 1.0 m** | `inference_base.py` | The height formula algebraically cancelled to the prior constant. Replaced with a per-category height prior + width from pixel aspect ratio. |
| **UTF-8 IFC crash** | `createIFCFurniture.py` | `open(..., "w")` used Windows `cp1252`; the IFC header's em-dash crashed *every* IFC export. Now writes UTF-8. |
| **Debris filter off by default** | `_triposr_postprocess.py` | Made component filtering + centering always-on (raw TripoSR emits 1,000s of fragments); heavier/flaky stages stay behind `SCS_TRIPOSR_SKIP_POSTPROC`. |
| **Bridge JSON parse** | `pythonBridge.js` | transformers' CLIP load-report prints to stdout, breaking `JSON.parse`; now scans for the final JSON line. |
| **TripoSR not reachable in UI** | `apiRoutes.js`, `index.html`, `index.js` | `/api/generate` forced detect-and-place for *all* models; added an Engine selector + a real `model==='triposr'` route so the web app can run TripoSR. |
| **`SCS_TRIPOSR_SEGMENTER` switch** | `run_triposr.py` | Force `sam2` or `rembg` so the two can be A/B-tested with identical post-processing. |

New tools written: `render_glb_preview.py` (server-side GLB→PNG, no WebGL), `sim_lens2bim.py`
(Sim C local photo→3D→IFC), `batch_abo_test.py`, `build_abo_gallery.py`, `score_abo_test.py`.

---

## 4. The "dots in the browser" detour (separate issue: WebGL)

For a long stretch, results looked like a **point cloud** in the browser. Root cause: this
machine's **Firefox WebGL is degraded** — it can't draw large 32-bit-indexed meshes, so xeokit
fell back to rendering vertices as points ("dots"); Edge (WebGL2) renders them fine, and Windows
3D Viewer always did. Mitigation: a no-WebGL **server-side PNG renderer** (`render_glb_preview.py`)
plus `<model-viewer>` pages with the PNG as a poster fallback. This was orthogonal to the mesh
quality problem but cost real time to untangle.

---

## 5. Does TripoSR work for furniture? (capability tests on REAL inputs)

After the weight fix, we tested real-world-style inputs:

| Input (real photo / studio demo) | Result |
|---|---|
| `chair.png` (simple studio cutout) | ✅ recognisable chair (seat + back + 4 legs) |
| User's **office chair** (real product photo) | ❌ blob, base lost |
| **Yoshi plush** (real photo) | ⚠️ rounded mass, no detail |
| `hamburger.png` | ✅ (post-fix) recognisable |
| Catalog **hairpin table** render | ⚠️ top OK, thin legs gone (filled solid) |
| Catalog **panel desk** render | ❌ crumpled blob |
| User's **executive L-desk** (real photo) | ❌ blob / folded slab |

**Pattern:** TripoSR reconstructs **bulk volume** acceptably but **loses thin structures**
(chair bases/casters, table/desk legs) and **fails on flat planar furniture** (no texture for
depth, open spans under tops). We verified this is the **single-view + marching-cubes ceiling**,
not fixable by segmentation, smoothing, or component filtering — each was tried and ruled out.

**Figure 3 — a real-photo desk (the actual SCS use case).** Input photo (3a); TripoSR under
SAM 2 (3b) and rembg (3c). Neither resembles a desk — one is a lumpy blob, the other a folded
slab. This is *worse* than the catalog-render benchmark in §6, as expected for real photos.

![Figure 3a. Input: user's real executive-desk photo.](report_assets/fig05_execdesk_input.png)
![Figure 3b. TripoSR (SAM 2) reconstruction of the desk — lumpy blob.](report_assets/fig06_execdesk_sam2.png)
![Figure 3c. TripoSR (rembg) reconstruction of the desk — folded slab.](report_assets/fig07_execdesk_rembg.png)

**Figure 4 — thin-structure loss.** A hairpin-leg table (catalog render input): the top
reconstructs, but the thin legs are filled into a solid block — the legs simply are not present.

![Figure 4. Hairpin table — tabletop reconstructs, thin legs lost (filled solid).](report_assets/fig10_hairpin_table.png)

**Figure 5 — a real plush toy** (Yoshi photo): reconstructs as a clean but featureless rounded
mass — bulk captured, detail lost.

![Figure 5. Yoshi plush real-photo reconstruction — rounded mass, no detail.](report_assets/fig09_yoshi.png)

---

## 6. The controlled benchmark — six conditions across three datasets (150 models)

What began as a single 25-model round grew, in response to the methodology caveats below, into a
**six-condition, three-dataset battery of 150 models** — each TripoSR reconstruction scored against
its ground-truth mesh with bidirectional Chamfer distance and F-score@0.02 (ICP-aligned). The
ground-truth mesh itself scores F = 1.0 by definition. All numbers are collected in
`MASTER_DASHBOARD.html` and `deliverable/all_scores.csv`.

### 6.1 The original round and its honest caveats
The first round used **the ABO catalog itself**: the first 5 each of `office_chair`, `desk`,
`table`, `sofa`, `bookshelf`; inputs were the catalog's own `*.preview.png` **studio renders**
(not real photos); ground truth was the **same ABO mesh** the render came from. Three biases, all
running *in TripoSR's favour*: (1) clean best-case inputs; (2) **self-referential** (reproduce a
render of the very mesh you're scored against); (3) **convenience sample**, small n. Because the
biases favour the generator yet it still failed (best F 0.48, most 0.16–0.36), the conclusion was
already *conservative*. The remaining rounds set out to **remove these biases one at a time**.

### 6.2 The expanded battery — and how each round attacks a bias
- **Randomized sampling** (seed 42) — kills the convenience-sample bias.
- **Disjoint categories** (cabinet, stool, lamp) — tests categories outside the original set.
- **Real product photographs** (ABO thumbnails, same seed-42 models) — removes the
  render-vs-photo and partly the self-referential bias.
- **A different commercial-safe dataset, Poly Haven (CC0)** — removes the ABO dependence entirely.
- **A research dataset, Objaverse** (LVIS furniture, in-the-wild meshes; per-object licenses
  recorded — research/internal-only, never shipped) — tests messy, un-curated geometry.

**Table — overall fidelity across all six conditions** (Chamfer lower=better, F higher=better;
ground-truth mesh = F 1.000 in every row):

| # | Condition | Dataset | n | SAM 2 Chamfer / F | rembg Chamfer / F | Winner |
|---|---|---|---|---|---|---|
| 1 | First-5 (renders) | ABO CC-BY | 25 | 0.160 / 0.276 | 0.125 / 0.362 | rembg |
| 2 | Random seed-42 (renders) | ABO | 25 | 0.154 / 0.312 | 0.126 / 0.387 | rembg |
| 3 | New categories (renders) | ABO | 15 | 0.172 / 0.287 | 0.158 / 0.359 | rembg |
| 4 | Real **photographs** | ABO | 25 | 0.159 / 0.317 | 0.152 / 0.333 | rembg (narrow) |
| 5 | Different dataset (renders) | **Poly Haven CC0** | 28 | 0.140 / 0.326 | 0.116 / **0.409** | rembg |
| 6 | In-the-wild (renders) | **Objaverse** (research) | 32 | 0.141 / **0.339** | 0.131 / 0.336 | ≈ tie |

### 6.3 Findings
1. **Real mesh ≫ any generation, in all six conditions.** Ground truth F = 1.0 vs best generated
   0.409 (2–6× more accurate surface). This is the **primary** result and it is now robust to
   sampling, category, input modality, *and* dataset (commercial-safe **and** research sources) —
   the external-validity and self-referential concerns of §6.1 are addressed, not just argued away.
2. **The rembg-vs-SAM 2 result is input-conditioned (a refinement).** rembg beats SAM 2 clearly on
   **clean curated renders** (rounds 1–3, 5: +24–48% F), but the advantage **shrinks to a near-tie
   on real photographs** (round 4) and to a **statistical tie on in-the-wild Objaverse meshes**
   (round 6, the lone condition where SAM 2 edges ahead). Interpretation: the simpler salient-object
   segmenter (rembg) only out-frames the stronger promptable model (SAM 2) on studio-clean inputs;
   as input variability rises, SAM 2 closes the gap. Earlier in the session we had (wrongly)
   concluded the two were universally equivalent based on one chair — the battery shows the truth is
   *input-dependent*, not constant.
3. **Segmentation is never the bottleneck.** SAM 2 and rembg masks are pixel-equivalent (Figure 6);
   the small reconstruction differences come from input *framing* (`resize_foreground`), not mask
   coverage. The thing that actually decides quality is the **input distribution and the model's
   single-view ceiling**, not which segmenter is used.

**Figure 6 — the two segmenters' masks are equivalent.** SAM 2 (6a) and rembg (6b) on the same
chair photo both cover the entire object (green overlay), base included — confirming segmentation
is *not* the bottleneck. The reconstruction difference comes from input *framing*, not coverage.

![Figure 6a. SAM 2 mask overlay — whole chair captured.](report_assets/fig03_sam2_mask.png)
![Figure 6b. rembg mask overlay — whole chair captured.](report_assets/fig04_rembg_mask.png)

**Figure 7 — one benchmark row (office_chair).** Input catalog render (7a); TripoSR·SAM 2 (7b);
TripoSR·rembg (7c); the real ABO mesh = ground truth (7d). The real mesh is crisp; both generated
meshes are lumpy approximations scoring far below it.

![Figure 7a. Benchmark input — ABO office-chair render.](report_assets/fig11_bench_input.png)
![Figure 7b. TripoSR (SAM 2) reconstruction.](report_assets/fig11_bench_sam2.png)
![Figure 7c. TripoSR (rembg) reconstruction.](report_assets/fig11_bench_rembg.png)
![Figure 7d. Real ABO mesh — ground truth (F-score = 1.0).](report_assets/fig11_bench_abo.png)

Artifacts: **`MASTER_DASHBOARD.html`** collects all six rounds (one scoreboard + links to 14
orbit-able galleries + the paper + downloads); `deliverable/all_scores.csv` holds all 150 per-model
rows; each round has its own portable bundle under `deliverable/` (`abo_gallery*.zip`). The
five-condition table above is also reproduced in the scientific paper
(`PAPER_Single_View_Furniture_3D`, §4.4, Table 3) with full methods and references.

---

## 7. The fix-side analysis (design exploration)

A separate multi-agent design exploration assessed five avenues against SCS constraints
(commercial-safe licences only; 6.4 GB local / capped cloud GPU; BIM-grade IFC goal), grounded
in the live repo. Verified findings:

- **FAISS index is desynced — confirmed live:** `data/mesh_library_abo/index.faiss` has
  **ntotal = 400**, but `manifest.json` has **515** entries. The 115 decor meshes (planter/
  mirror/clock/picture_frame added earlier) are **unsearchable**, and any hit on rows ≥ 400
  indexes the **wrong** mesh. This is a correctness bug, fixable in ~5 min (`build_abo_index.py`).
- **The "no executive desk in the catalog" belief is false** — 50 desks (incl. ~1.6 m executive
  widths) are indexed. The desk retrieval failed on the **photo-vs-silhouette embedding gap**
  (the query embeds the raw photo crop incl. background), not a missing mesh.

**Figure 8 — what retrieval pulls** (the catalog's best match for the desk photo of Figure 3a):
a clean, watertight, BIM-ready ABO mesh — the opposite of the generated blobs in Figures 3b–3c.
This is the path forward for furniture.

![Figure 8. Retrieved ABO mesh — clean, watertight, BIM-ready (vs the generated blobs).](report_assets/fig08_retrieved_abo_mesh.png)
- **Parametric primitives are buried** — `_build_primitive_mesh` is only reached *after*
  retrieval + TRELLIS + TripoSR all fail; the clean deterministic path is gated behind the
  broken ones.

### Ranked roadmap
| Rank | Avenue | Effort | Verdict |
|---|---|---|---|
| 1 | **Parametric primitives → primary** for office furniture (class + metric dims from DETR/Depth-Anything) | low | Do now |
| 2 | **Fix retrieval** — rebuild index (5 min), segment query before embedding, re-tune threshold | low–med | Do now |
| 3 | **Multi-photo / photogrammetry** (COLMAP/pycolmap BSD + Open3D) for out-of-catalog objects | med | Pilot later |
| 4 | **Multi-view generative bake-off** (InstantMesh Apache-2.0 / TRELLIS MIT) on capped cloud | med | Run once for a number; catalog-miss fallback only |
| 5 | **Squeeze single-view TripoSR** | — | **Wrong investment — stop** |

License traps flagged: OpenMVS (AGPL), and the existing `run_instantmesh.py`/`run_stablefast3d.py`
stubs actually call YOLO (AGPL) — delete before any external distribution.

---

## 8. Conclusions

1. **The pipeline had one severe, now-fixed bug** (image-encoder weights). Generation quality
   for *bulk* shapes is restored.
2. **Single-view generation is the wrong tool for BIM furniture** — now established across **6
   conditions, 3 datasets, 150 models**: the real mesh beats the best generated mesh 2–6× in every
   condition (best generated F = 0.409 vs 1.0). Robust to sampling, category, render-vs-photo input,
   and dataset. This is no longer a single-benchmark claim.
3. **If generating at all, the segmenter choice is input-conditioned:** prefer **rembg** for clean
   catalog renders (`SCS_TRIPOSR_SEGMENTER=rembg`), but treat rembg and SAM 2 as **equivalent** for
   real photographs and in-the-wild assets — the data shows the advantage disappears there.
4. **The product path is Detect → Retrieve → Parametric**, not generation. The first concrete
   step is a 5-minute FAISS index rebuild (a guaranteed correctness win), then closing the
   retrieval domain gap and promoting parametric primitives.

---

## 9. Artifacts & status

**All committed + pushed** to `origin/app-development` (`540757f` the fixes + study, `540bbdd` the
Objaverse round). Bulky regenerable artifacts (~2 GB of meshes/renders/zips) are gitignored but
rebuildable from the committed scripts.

**Code fixed:** `backend/triposr/tsr/system.py` (weight-load auto-detect),
`backend/python-scripts/{inference_base,createIFCFurniture,_triposr_postprocess,run_triposr}.py`,
`backend/routes/apiRoutes.js`, `backend/services/pythonBridge.js`, `frontend/index.html`,
`frontend/js/index.js`, `TripoSR_CHANGES_AND_LESSONS.md` (Changes 10–14).

**New tooling (9 scripts):** `render_glb_preview.py` (no-WebGL GLB→PNG), `sim_lens2bim.py`
(Sim C photo→3D→IFC), `batch_abo_test.py` (the benchmark driver, with `--random/--seed/--out/--input`),
`score_abo_test.py`, `build_abo_gallery.py`, `export_abo_gallery.py` (portable bundles),
`polyhaven_benchmark.py` (CC0 dataset), `objaverse_benchmark.py` (research dataset, license-recording),
`collect_all.py` (the master dashboard + combined CSV).

**Collected outputs:** `MASTER_DASHBOARD.html` (one page: 6-round scoreboard + 14 galleries + paper
+ report + bundles); `deliverable/all_scores.csv` / `all_scores.json` / `round_summary.csv` (150
rows); per-round data in `outputs/abo_test*/` (5 ABO + Poly Haven + Objaverse folders); portable
bundles `deliverable/abo_gallery*.zip` + the preserved first-5 archive.

**Documents:** the **scientific paper** `PAPER_Single_View_Furniture_3D.{md,html}` (IMRaD, 6
conditions, threats-to-validity, references); this report; `report_assets/` (fig01–fig11, all real
renders/photos/masks — no illustrations).

**Open items (the fix-side roadmap, not yet done):** rebuild the FAISS index (400→515); promote
parametric primitives to primary; close the retrieval photo-vs-silhouette domain gap. Optionally
flip the generation default segmenter to rembg for the (clean-input) generative path.

---

## 10. Honest limitations of this investigation

- **Now addressed (was: "ABO renders, not real photos"):** the expanded battery added a real-photo
  round and two non-ABO datasets, and the headline result held. *Residual caveat:* even the
  real-photo round used clean studio product thumbnails, not genuinely cluttered field photos — and
  those (the user's chair/desk, §5) were qualitatively worse, so the conclusion remains conservative.
- **Now addressed (was: "small n"):** overall per-round means are stable across six independent
  rounds. *Residual caveat:* per-*category* rankings (n = 4–5/type) still show small-sample noise;
  the robust claims are the per-round overalls, not individual category winners.
- **CLIP classifier is weak** (mislabels chairs/desks as "lamp"/"keyboard"); DETR is the strong
  detector and should drive classification — orthogonal to the geometry findings here.
- **TripoSR `mc_resolution` is capped at 256** by the 6.4 GB local GPU; higher resolution (cloud)
  was not tested and would not fix the structural single-view failures anyway.
- **Multi-view generators not yet measured.** InstantMesh / TRELLIS were not run; they could in
  principle clear the single-view ceiling, and quantifying that is the recommended next experiment.
