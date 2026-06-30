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
- A controlled 25-model benchmark (Chamfer + F-score vs ground truth) showed: **the real ABO
  catalog mesh beats any generated mesh by 2–6×**, and **rembg beats SAM 2** as the segmenter
  for feeding TripoSR (overall F 0.362 vs 0.276) — overturning an earlier "they're equivalent"
  assumption.
- **Methodology caveat (important):** the 25-model benchmark used the **ABO catalog's own
  renders as inputs**, scored against those same meshes — a clean, best-case, partly
  self-referential setup. Real-photo tests (done separately) were worse. See §6.
- **Recommendation:** stop generating furniture; route Detect → Retrieval (fix the broken
  FAISS index first) → parametric primitive fallback. Keep generation only as a cloud,
  multi-view, catalog-miss fallback.

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

## 6. The controlled benchmark — and its sample-data caveat

### What the sample was (READ THIS — it qualifies every number below)
The 25-model benchmark used **the Amazon Berkeley Objects (ABO) catalog itself** as the sample:
- **25 meshes**: the first **5 each** of `office_chair`, `desk`, `table`, `sofa`, `bookshelf`
  from the local 515-mesh ABO library (a convenience sample, not random).
- **Inputs were the catalog's own `*.preview.png` renders** — clean, single-object, white/neutral
  background, good 3/4 framing. These are **studio renders of the meshes**, **not real photos**.
- **Ground truth for scoring was the same ABO mesh** the input render came from.

**Why this matters (the bias, stated honestly):**
1. **Best-case inputs.** Clean cutouts on plain backgrounds are the *easiest* case for TripoSR.
   Real photos (busy backgrounds, lighting, occlusion) are harder — and indeed the real-photo
   tests in §5 came out *worse* than these benchmark numbers.
2. **Partly self-referential.** The input is a render *of* the ground-truth mesh, so the task is
   "reproduce a mesh you were shown a picture of." This flatters TripoSR relative to a
   from-scratch real-world photo.
3. **Convenience sample.** First-5-per-type, not randomly drawn; small n (5/type) → per-type
   numbers are indicative, not statistically tight.

**Why the conclusion still holds despite the bias:** the bias runs *in TripoSR's favour*, yet it
**still failed** (best F-score 0.48, most 0.16–0.36). If it can't reproduce a clean catalog
render of furniture, it certainly can't reconstruct a real office-furniture photo. So the
"generation is insufficient for furniture" conclusion is **conservative**, not overstated.

### The scoreboard (Chamfer distance — lower better; F-score@0.02 — higher better)
Each TripoSR reconstruction scored against its ABO ground-truth mesh. The ABO mesh itself scores
F = 1.0 by definition (it is the ground truth).

| Type | SAM 2 — Chamfer / F | rembg — Chamfer / F | Winner |
|---|---|---|---|
| office_chair | 0.120 / 0.319 | 0.120 / 0.347 | ~tie |
| desk | 0.248 / 0.160 | **0.169 / 0.263** | rembg |
| table | 0.135 / 0.358 | **0.095 / 0.479** | rembg |
| sofa | **0.117 / 0.329** | 0.153 / 0.259 | SAM 2 |
| bookshelf | 0.178 / 0.212 | **0.090 / 0.462** | rembg |
| **OVERALL** | 0.160 / 0.276 | **0.126 / 0.362** | **rembg** |

### Findings
1. **ABO mesh ≫ any generation** — ground truth F = 1.0 vs best generated 0.48 (2–6× more
   accurate surface). The real catalog mesh wins every row.
2. **rembg objectively beats SAM 2 for TripoSR** — overall F 0.362 vs 0.276 (~31% better),
   lower Chamfer. This **overturned** the earlier session assumption that they were equivalent
   (that was true only for the one chair tested; the chair row here is indeed a tie). rembg wins
   clearly on flat/planar items (desk, table, bookshelf); sofa is the lone SAM 2 win.
3. **"Best segmenter" ≠ "best segmenter for TripoSR."** SAM 2 is the stronger segmentation model,
   but rembg's salient-object cutout frames furniture more consistently for `resize_foreground`,
   which TripoSR is sensitive to.

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

Artifacts: visual gallery `outputs/view_abo_gallery.html` (75 orbit-able meshes), raw numbers
`outputs/abo_test/scores.json`, meshes `outputs/abo_test/`.

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
2. **Single-view generation is the wrong tool for BIM furniture** — proven on real photos and,
   conservatively, on best-case catalog renders. Even the favourable benchmark tops out at
   F = 0.48 vs the real mesh's 1.0.
3. **If generating at all, use rembg** (data-backed; `SCS_TRIPOSR_SEGMENTER=rembg`).
4. **The product path is Detect → Retrieve → Parametric**, not generation. The first concrete
   step is a 5-minute FAISS index rebuild (a guaranteed correctness win), then closing the
   retrieval domain gap and promoting parametric primitives.

---

## 9. Artifacts & status

**Code changed (uncommitted on `app-development` at time of writing):**
`backend/triposr/tsr/system.py`, `backend/python-scripts/{inference_base,createIFCFurniture,
_triposr_postprocess,run_triposr}.py`, `backend/routes/apiRoutes.js`,
`backend/services/pythonBridge.js`, `frontend/index.html`, `frontend/js/index.js`,
`TripoSR_CHANGES_AND_LESSONS.md` (Changes 10–14).
**New scripts:** `render_glb_preview.py`, `sim_lens2bim.py`, `batch_abo_test.py`,
`build_abo_gallery.py`, `score_abo_test.py`.
**Viewers (served by the Node app on :3000):** `view_abo_gallery.html`, `view_verdict.html`,
`view_execdesk_full.html`, `view_compare.html`, `view_desk.html`, `view_table.html`,
`view_triposr.html`.
**Data:** `outputs/abo_test/` (75 meshes + posters), `scores.json`, `results.json`.
**Figures:** `report_assets/` (fig01–fig11, embedded inline above; render in any Markdown viewer —
VS Code preview, GitHub). Each figure is a server-side render of an actual mesh produced this
session, or an actual input photo/mask overlay — no illustrations, all real outputs.

**Open items:** commit the fixes; rebuild the FAISS index (400→515); the design-roadmap work
(parametric-first, retrieval domain gap). Generation default segmenter could be flipped to rembg.

---

## 10. Honest limitations of this investigation

- **Benchmark sample is ABO catalog renders, not real photos** (see §6) — numbers are an *upper
  bound* on real-world TripoSR quality.
- **Small n** (5 per type) — per-type rankings are indicative.
- **CLIP classifier is weak** (mislabels chairs/desks as "lamp"/"keyboard"); DETR is the strong
  detector and should drive classification — orthogonal to the geometry findings here.
- **TripoSR `mc_resolution` is capped at 256** by the 6.4 GB local GPU; higher resolution (cloud)
  was not tested and would not fix the structural single-view failures anyway.
