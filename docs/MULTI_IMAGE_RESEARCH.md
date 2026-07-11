# Multi-Image → 3D: License-Verified Research & the App's Second Mode

**Date:** 2026-07-11 · **Scope:** a user photographs ONE furniture object from
several angles (2–8 casual phone shots, no calibration) and gets a cleaner,
fuller mesh than any single-image AI can produce. Same hard rules as the
single-image audit ([HUGGINGFACE_MODEL_NARROWING.md](HUGGINGFACE_MODEL_NARROWING.md)):
royalty-free commercial for code AND weights, EU allowed, no NC / AGPL / caps.
All license claims below were verified against primary LICENSE files and HF
model cards on 2026-07-11.

## Headline result

Only **two** paths combine true multi-photo input with royalty-free licensing,
and both need one dependency swap. Everything famous in this field is
license-trapped.

### The chosen product path (Mode 2 of the app)

| Component | Role | License | Caveat |
|---|---|---|---|
| **TRELLIS v1 `run_multi_image`** | 2–8 unposed photos → complete GLB mesh | MIT code + MIT weights | tuning-free bolt-on ("may not give the best results"); NC submodules on the TEXTURE path only — see below |
| **MapAnything (`facebook/map-anything-apache`)** | metric scale + camera poses from the same photos | Apache-2.0 (this checkpoint ONLY — the default `facebook/map-anything` is CC-BY-NC) | trained on fewer datasets than the NC variant |
| Depth Anything 3 (Small/Base/Metric-L/Mono-L) | alternative metric/pose building block | Apache-2.0 (these variants ONLY — Large/Giant are CC-BY-NC) | — |

Why the pairing matters for BIM: TRELLIS output is **scale-free**; MapAnything
returns **metric** point maps — together they give a full mesh *with real-world
dimensions*, which is exactly what the IFC export needs.

**TRELLIS commercial caveat (applies to our single-image TRELLIS use too):**
the TRELLIS *geometry* path is clean — FlexiCubes mesh extraction was relicensed
Apache-2.0 by NVIDIA. But three submodules of the as-shipped pipeline are
non-commercial: `diffoctreerast` and the mip-splatting `diff-gaussian-rasterization`
(Inria: "THE USER CANNOT USE, EXPLOIT OR DISTRIBUTE THE SOFTWARE FOR COMMERCIAL
PURPOSES") and `nvdiffrast` (NVIDIA: non-commercial research/evaluation only) —
these sit on the radiance-field and **texture-baking** paths. Pragmatic v1:
**ship untextured geometry** (BIM/IFC barely needs baked textures) — that path
is MIT/Apache-clean today; later swap the Gaussian rendering to gsplat
(Apache-2.0) if textures become a requirement.

### The "orbit mode" power-user path (20–40 photos)

Classical photogrammetry **cannot** serve 2–8 casual photos (it needs 60–80%
overlap between successive shots — realistically 20–30 photos minimum, 50+
comfortable; furniture is its documented worst case: textureless laminate,
glossy varnish, thin chair legs). But as an optional "walk around the object"
premium mode the license-clean stack is:

- **COLMAP** (BSD-3) — **must be a curated build**: `-DLSD_ENABLED=OFF` (bundled
  LSD is AGPL and ON by default!), no SiftGPU (UNC research-only — CPU VLFeat
  SIFT instead), `-DCGAL_ENABLED=OFF`. **A stock COLMAP binary is NOT safe to ship.**
- **GLOMAP** (BSD-3) for fast global poses; **hloc + LightGlue + ALIKED/XFeat**
  (Apache/BSD) for learned matching (NOT SuperPoint/SuperGlue — Magic Leap
  non-commercial).
- **gsplat 2DGS** (Apache-2.0 clean-room — NOT the Inria 3DGS lineage) →
  TSDF/Poisson meshing with **Open3D** (MIT) → **instant-meshes** (BSD-3) retopo.
- Or single-tool: **Meshroom/AliceVision** (MPL-2.0) end-to-end.
- **BANNED here:** OpenMVS (AGPL — the usual COLMAP companion), OpenSplat (AGPL),
  PyMeshLab/MeshLab (GPL-3), original Inria 3DGS + SuGaR family (non-commercial).

### Famous but BANNED for multi-image (pin to the wall)

DUSt3R · MASt3R · MUSt3R · Pow3R (Naver NC) — VGGT-1B · Fast3R · MV-DUSt3R+ ·
default `facebook/map-anything` (Meta CC-BY-NC/FAIR-NC) — CUT3R · Spann3R ·
SLAM3R (CC-BY-NC-SA) — Pi3 weights (CC-BY-NC) — DA3 Large/Giant (CC-BY-NC) —
Hunyuan3D-2mv (EU territory exclusion) — SpaRP (no permissive weights released) —
SuperPoint/SuperGlue (Magic Leap NC) — OpenMVS/OpenSplat (AGPL) —
nvdiffrast/nvdiffrec/instant-ngp (NVIDIA NC).

**Watch-list:** MV-SAM3D (third-party multi-view extension of SAM 3D Objects,
SAM License, pose-free, GLB out; early-stage and its preprocessing defaults to a
CC-BY-NC Depth Anything 3 checkpoint — usable only after a one-line swap to an
Apache DA3 variant). Re-evaluate when it matures.

## New single-image compliance findings (same audit session)

- **InstantMesh is NOT product-usable**: its own code is Apache-2.0, but the
  pipeline hard-requires **Zero123++ weights (CC-BY-NC 4.0)** — "you cannot use
  the model (or its derivatives) in a commercial product pipeline, but you can
  still use the outputs from the model freely." Status downgraded to
  **benchmark-only** (same tier as SF3D). It stays in the accuracy studies;
  it must never ship in the app's engine selector.
- **TRELLIS.2 is single-image only** — no `run_multi_image`; also inherits
  nvdiffrast/nvdiffrec texture deps (same geometry-only guidance as v1).
- **Hunyuan under "research/student" use: still NO.** The Tencent Community
  License is a *territory exclusion* — the license is not granted in the
  EU/UK/South Korea *for any purpose*, so there is no research carve-out to rely
  on (unlike ordinary NC licenses). For the paper: cite Hunyuan's published
  numbers and document the exclusion — running the weights in Germany is
  unlicensed use.

## The app's two modes (design)

1. **Mode 1 — Single photo** (exists): photo → VRAM-gated engine selector →
   archetype repair packs → IFC4 gate → catalog with engine badge.
2. **Mode 2 — Multiple photos** (new): 2–8 photos of ONE object → TRELLIS
   `run_multi_image` (geometry) + MapAnything-apache (metric dims) → the SAME
   repair → IFC gate → catalog path, badged as its own engine (`TRL-MV`) so
   single- vs multi-image is directly comparable in the picker, the visualizer
   ("Multi-image" comparison group), and the per-AI IFC folders.

## Study E (planned): single vs multi-image, quantified

We have what most teams don't: ground-truth ABO meshes. Protocol: render N=4
known views of each GT object (front, ±45°, back) → feed to `run_multi_image` →
score with the identical Chamfer + F@0.02 / ICP / seed-42 protocol as Studies
A/C → compare against the same object's single-image score. This isolates the
multi-image gain with real ground truth. Pod-runnable with the TRELLIS env.

## Capture protocol for Mode 2 (user guidance)

- **4 photos is the sweet spot** (2 works, up to 8 fine): front, front-left ~45°,
  front-right ~45°, and **one back/back-quarter shot** — the back view is the
  single highest-value photo (it's exactly what single-image AI hallucinates).
- Object fully in frame, ~60–80% of frame, similar distance each shot;
  consistent lighting; avoid strong reflections; plain background helps
  (pipeline runs rembg per image).
- No poses, no overlap requirement, no calibration — these are independent
  conditioning views, not photogrammetry.
- If MapAnything runs alongside: adjacent shots should share some visible
  context (floor/wall) for its pose estimation.
