# TripoSR — Changes, Adaptations & Lessons Learned

**Project:** 3D Picture to IFC Modeling  
**Model:** stabilityai/TripoSR (Stability AI)  
**Document date:** 2026-04-30  
**Authors:** Dimi (engineering), Gulriz (research)

---

## What TripoSR is

TripoSR is a real trained neural network by Stability AI. It takes a single 2D photograph and reconstructs a 3D mesh. It was trained on approximately 800,000 3D objects from the Objaverse dataset.

- **Architecture:** Transformer encoder-decoder
- **Reconstruction method:** Marching cubes on a predicted 3D volume (density field)
- **Weights size:** ~1.3 GB, downloaded automatically from HuggingFace (`stabilityai/TripoSR`) on first run and cached locally
- **License:** MIT — free for commercial use
- **What we do NOT have in the repo:** The trained weights (too large for GitHub). Only the inference code and our pipeline around it.

---

## Change 1 — Replaced torchmcubes with scikit-image marching cubes

**File:** `backend/triposr/tsr/models/isosurface.py`  
**Why:** TripoSR's original code depends on `torchmcubes`, a C extension that has no compiled wheels for Python 3.14. On Python 3.14 the import fails immediately and the entire pipeline crashes before any inference runs.

**What we did:** Patched the `marching_cubes` function in `isosurface.py` to use `skimage.measure.marching_cubes` (scikit-image) as a drop-in replacement. No changes to the model weights or architecture.

**Two sub-bugs fixed during this:**
1. `"Surface level must be within volume data range"` — scikit-image requires the threshold to be strictly within the data range. Fixed by clipping: `np.clip(threshold, vol_min + 1e-6, vol_max - 1e-6)`
2. `"Negative strides not supported"` — scikit-image returns non-contiguous numpy arrays. Fixed by calling `.copy()` on both the vertices and faces arrays before converting to torch tensors.

**Lesson learned:** Python 3.14 is very new. Many ML C extensions (torchmcubes, xatlas, moderngl) have no wheels for it yet. When a dependency fails on a new Python version, patching with a pure-Python equivalent (scikit-image in this case) is faster than waiting for wheel support.

---

## Change 2 — Switched PyTorch from CPU to CUDA 12.6

**File:** `.env` (`USE_GPU=true`)  
**Command run:**
```bash
pip install torch torchvision --force-reinstall --index-url https://download.pytorch.org/whl/cu126
```

**Why:** The initial install had `torch 2.11.0+cpu` — no GPU support. The RTX 4050 Laptop GPU was present and detected by the NVIDIA driver (CUDA 12.7) but PyTorch was not using it.

**Result:**
- Before: CPU inference, ~10–20 minutes per image, marching cubes at 96³ resolution
- After: GPU inference on RTX 4050 (6GB VRAM), ~1–3 minutes per image, marching cubes at 256³ resolution

**Lesson learned:** `pip install torch` without specifying the index URL always installs the CPU build. The CUDA build must be explicitly requested with `--index-url https://download.pytorch.org/whl/cu126`. Running `python -c "import torch; print(torch.cuda.is_available())"` is the fastest way to verify GPU is active.

---

## Change 3 — Background removal with rembg (U²-Net)

**File:** `backend/python-scripts/run_triposr.py`  
**Library:** `rembg` (U²-Net neural network, MIT license)

**Why:** TripoSR requires a clean input image — foreground object on a gray background. If the raw photo is fed directly, the model tries to reconstruct the entire scene including desk, laptop, floor, and wall, producing garbage geometry.

**What we did:**
```python
rembg_session = rembg.new_session()
img_rgba = remove_background(Image.open(image_path), rembg_session)
img_rgba = resize_foreground(img_rgba, 0.85)
# Composite foreground onto gray background (TripoSR requirement)
img_arr = img_arr[:, :, :3] * img_arr[:, :, 3:4] + (1 - img_arr[:, :, 3:4]) * 0.5
```

**Install issue hit:** `pip install rembg` alone failed with `no onnxruntime backend`. Required `pip install "rembg[cpu]"` specifically.

**Lesson learned:** rembg's mask edges are imprecise — it tends to include surrounding warm-toned pixels (desk, lamp, yellow laptop screen) in the foreground region. This caused the mesh color to be skewed yellow in early runs. rembg is a practical baseline but SAM2 (Meta, Apache 2.0) would produce significantly cleaner masks with better edge quality.

---

## Change 4 — Mesh resolution increased to 256³ on GPU

**File:** `backend/python-scripts/run_triposr.py`

**What we did:**
```python
mc_resolution = 256 if device == "cuda" else 96
meshes = model.extract_mesh(scene_codes, True, resolution=mc_resolution)
```

**Why:** 96³ on CPU was the safe default to avoid multi-hour inference. At 256³ on GPU the voxel grid is 256×256×256 = ~16.7 million voxels vs 96³ = ~884,000 voxels. This is a 19× increase in geometric detail.

**Lesson learned:** Resolution is the single biggest lever for mesh quality in marching cubes reconstruction. The GPU makes this practical. Going above 256 would require more than 6GB VRAM.

---

## Change 5 — Component filtering (debris and spike removal)

**File:** `backend/python-scripts/run_triposr.py`

**Problem:** Raw TripoSR output contains:
- Floating debris — tiny disconnected mesh fragments with no structural meaning
- Spike artifacts — thin needle-like components formed when the density field has narrow high-density corridors

**What we did — evolution:**

*Version 1 (wrong):* Keep only the single largest component.
```python
mesh = max(components, key=lambda m: len(m.faces))
```
This discarded the chair legs entirely — they are separate geometry and smaller than the seat.

*Version 2 (current):* Keep all components above 0.5% of total faces AND with a compactness ratio above 4% (not needle-shaped):
```python
face_ratio = len(c.faces) / total_faces
compactness = extents.min() / extents.max()
if face_ratio >= 0.005 and not (compactness < 0.04 and face_ratio < 0.05):
    kept.append(c)
mesh = trimesh.util.concatenate(kept)
```

**Lesson learned:** Chair legs are geometrically separate from the seat in the marching cubes output. Any filter that only keeps the single largest component will always discard them. The 0.5% threshold keeps legs (which are ~2–8% of total faces) while dropping true debris (typically <0.1%).

---

## Change 6 — Mesh color: from UV projection to vertex colors to PBR material

**File:** `backend/python-scripts/run_triposr.py`

This went through three iterations:

**Version 1 — UV projection (failed)**  
Attempted to project the original photo onto the mesh as a texture. This sampled from the top-left of the original unmasked image, which contained the yellow laptop screen. Every mesh came out yellow-green.

**Version 2 — Vertex colors (failed in viewer)**  
Computed average foreground pixel color from the rembg alpha mask and assigned it as `mesh.visual.vertex_colors`. The color was more accurate but xeokit's `GLTFLoaderPlugin` does not render `COLOR_0` vertex attributes from GLB files. All meshes rendered white in the browser.

**Version 3 — PBR material baseColorFactor (current, working)**  
```python
mesh.visual = trimesh.visual.TextureVisuals(
    material=trimesh.visual.material.PBRMaterial(
        baseColorFactor=np.array([r, g, b, 1.0]),
        roughnessFactor=0.7,
        metallicFactor=0.0,
    )
)
```
This writes a GLTF `pbrMetallicRoughness.baseColorFactor` which xeokit reads and renders correctly. Color derived from the mean of foreground pixels (alpha > 64) from the rembg RGBA output.

**Lesson learned:** xeokit SDK v2.6.108 ignores vertex color attributes (`COLOR_0`) in GLB files. Colors must be embedded as GLTF PBR material properties. This is a known xeokit limitation and applies to any model loaded via `GLTFLoaderPlugin`.

---

## Change 7 — Laplacian smoothing

**File:** `backend/python-scripts/run_triposr.py`

```python
trimesh.smoothing.filter_laplacian(mesh, iterations=5)
```

**Why:** Marching cubes at any resolution produces a stepped, faceted surface. The voxel grid boundary creates a staircase effect on diagonal surfaces. Laplacian smoothing averages each vertex toward its neighbors, rounding out the facets.

**Evolution:** Started at 3 iterations (gave a slightly angular look). Increased to 5 on GPU where the higher base resolution means smoothing removes fewer details.

**Lesson learned:** Too many iterations (>8) causes the mesh to lose volume — it shrinks inward. 5 is the practical balance between smooth appearance and shape preservation.

---

## Change 8 — Orientation detection and correction

**File:** `backend/python-scripts/run_triposr.py`

TripoSR outputs the mesh in camera space. Depending on the photo's framing, the reconstructed object is often upside-down or tilted.

**Version 1 (centroid heuristic — unreliable):**
```python
centroid_y = mesh.vertices[:, 1].mean()
if centroid_y > 0.05:
    R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    mesh.apply_transform(R)
```
This failed in practice. For a chair with a heavy 5-spoke base, the base geometry pulled the centroid below Y=0 even when the chair was upside down. The condition never triggered when needed.

**Version 2 (face normal area — current):**
```python
up_area   = face_areas[face_normals[:, 1] >  0.5].sum()
down_area = face_areas[face_normals[:, 1] < -0.5].sum()
if down_area > up_area:
    R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    mesh.apply_transform(R)
```
Measures total face surface area pointing upward vs downward. The seat and back of a chair are large flat upward-facing surfaces — if more surface area faces down than up, the mesh is inverted.

**Lesson learned:** Positional heuristics (centroid) are fragile because object geometry varies. Normal-based detection is more robust because it captures the actual surface orientation, not just where the mass sits.

---

## Change 9 — Rotational symmetry enforcement (attempted, reverted)

**File:** `backend/python-scripts/run_triposr.py`  
**Status:** REVERTED

**What was attempted:** Isolate the bottom 28% of the mesh (base zone), split into spoke components, take the best-formed spoke, rotate it N times to create identical copies, replace the original uneven base.

**Why it failed:** The base zone cut split the mesh incorrectly — it severed the upper body geometry at the cut line, creating a jagged disconnected boundary. The rotated spokes did not align with the chair body. The resulting mesh was heavily distorted and unrecognizable.

**Lesson learned:** Geometric post-processing that modifies topology (cutting, reattaching, replacing parts) is extremely brittle when applied to neural network outputs. The mesh boundary between base and body is not a clean horizontal plane — it is irregular. The correct solution to asymmetric legs is using a multi-view model (InstantMesh) that sees all sides of the object before reconstruction, not post-hoc geometric manipulation.

---

## Current pipeline summary

```
Input photo
    │
    ▼
rembg (U²-Net)
  Remove background, composite on gray, resize foreground to 85%
    │
    ▼
TripoSR inference (GPU, RTX 4050)
  Encode image → predict 3D density field → marching cubes at 256³
    │
    ▼
Component filtering
  Keep components ≥ 0.5% of faces, reject compactness < 4% spikes
    │
    ▼
Center at origin
    │
    ▼
Orientation correction
  Face normal area vote: flip if down_area > up_area
    │
    ▼
Laplacian smoothing (5 iterations)
    │
    ▼
PBR material (mean foreground color → baseColorFactor)
    │
    ▼
GLB export (trimesh)
    │
    ▼
xeokit viewer → IFC export
```

---

## Known limitations of TripoSR (structural, cannot be fixed in post-processing)

| Limitation | Example observed | Root cause |
|---|---|---|
| Hidden surfaces missing | Desk back leg absent | Single view — model never sees the back |
| Asymmetric repeated geometry | Chair legs all different shapes | Each spoke reconstructed independently from partial visibility |
| Flat surface distortion | Table top comes out slightly wavy | No texture variation on uniform surfaces confuses density prediction |
| No material differentiation | Chair fabric and desk laminate get same material | Model outputs geometry only, no material segmentation |
| Thin geometry artifacts | Desk legs, armrests under-resolved | Thin features fall between marching cubes voxels at any resolution |
| Single averaged color | Two-tone desk (white top, dark body) gets one blended color | One PBR material per mesh, no UV texture baking |

---

## What would actually fix these limitations

| Limitation | Real fix | Roadmap sprint |
|---|---|---|
| Hidden surfaces / asymmetric legs | InstantMesh — generates 6 views before reconstruction | Sprint 1 |
| No material differentiation | Hunyuan3D-2 — outputs separate PBR material maps (albedo, roughness, metallic, normal) | Sprint 7 |
| Single averaged color | Texture baking with UV unwrapping (requires xatlas — no Python 3.14 wheel yet) | Blocked |
| Object type / surface material recognition | YOLO fine-tuned classifier + material lookup table per object type | Sprint 4 |

---

# 2026-06-29 session — SAM2, metric-scale fixes, IFC encoding, and the Lens2BIM local sim

*Authors: Dimi (engineering). These extend the pipeline above; the inline rembg /
Laplacian / component-filter steps from Changes 3–9 now live behind SAM2 and the
centralised `_triposr_postprocess.py` (post-processing currently **default-off**,
`SCS_TRIPOSR_SKIP_POSTPROC` defaults to "1", because the topology-editing steps
were flaky — see Change 9).*

## Change 10 — SAM2 segmentation adopted (the upgrade predicted in Change 3)

**File:** `backend/python-scripts/run_triposr.py` (`_segment_foreground`)

Change 3's lesson said SAM2 would give cleaner masks than rembg. It's now the
primary segmenter (`sam2.1_hiera_tiny`, centre-point grid prompt), with **rembg as
the fallback** if SAM2 fails. Measured coverage on test objects: 99.4% (filing
cabinet stub), 23.9% (chair on white). Dominant colour is now picked by **k-means
(k=3)** on the SAM2 mask instead of a plain mean — avoids the warm-tone background
leak that skewed early meshes yellow.

**Lesson learned:** the Change 3 prediction held — SAM2 edges are materially cleaner
than rembg, and a mask good enough to drive both the geometry *and* the colour
k-means is worth the extra weight file.

## Change 11 — Metric-scale estimation: two bugs fixed

**File:** `backend/python-scripts/inference_base.py` (`estimate_metric_scale`)

Single-image depth (Depth-Anything-V2) is used to estimate real-world dimensions
for the IFC. Two defects, both found by actually running it:

1. **Crash — `boolean index did not match… size 256 vs 300`.** The SAM2 mask passed
   in by `run_triposr` has already been through `resize_foreground`, so its shape
   ≠ the original image. The code resized the mask by `depth_shape / original_image_shape`,
   producing a 300-row mask indexed against a 256-row depth map. **Fix:** resize the
   mask from its **own** shape to the depth shape.
2. **Height was always 1.0 m.** The old formula `prior * (pixel_h/H_img) * (H_img/pixel_h)`
   algebraically cancels to `prior` — so every object got the flat 1.0 m fallback even
   when it didn't crash. **Fix:** a per-category height prior (`_HEIGHT_PRIORS`, keyed
   on the CLIP label — e.g. office_chair 1.05 m, desk 0.74 m, filing_cabinet 1.32 m)
   with **width derived from the object's pixel aspect ratio** and depth from the
   relative depth extent. The CLIP label is now threaded in from `run_triposr`.

**Lesson learned:** (a) never resize a mask against the *original* image dims once
something upstream has already reshaped it — resize against its own shape. (b) Watch
for formulas that algebraically collapse to a constant; "it returns a plausible
number" hid a no-op for a long time. A monocular image has no absolute scale, so an
explicit category prior is the honest model, not a depth-derived "measurement".

## Change 12 — IFC writer crashed on Windows (`cp1252` vs UTF-8)

**File:** `backend/python-scripts/createIFCFurniture.py`

`open(output_ifc, "w")` used Python's platform default encoding, which on this
Windows box is `cp1252`. The IFC header contains an em-dash (—), so **every IFC
export raised `UnicodeEncodeError`** — not just the sim. **Fix:** `open(..., "w",
encoding="utf-8")`.

**Lesson learned:** on Windows, always pass `encoding="utf-8"` to `open()` for any
text the program generates. The default is locale-dependent and will silently work
in ASCII tests, then crash the first time a non-ASCII glyph (em-dash, ×, °) appears.

## Change 13 — Lens2BIM: Sim C (Local) Photo → 3D → IFC

**File:** `backend/python-scripts/sim_lens2bim.py` (new)

A single named, locally-runnable simulation that chains the whole commercial-safe
pipeline per photo: **SAM2 → TripoSR (256³, GPU) → fine-tuned CLIP → metric scale →
IFC4**, writing a `.glb` + `.ifc` + `summary.json` per run. Fits the 6.4 GB RTX 4050
(TripoSR only — the 16/32 GB cloud models of the Sim A bake-off can't run here).
First green run: `chair.png` → 1.27 M-face GLB + valid IFC4 in **25.8 s**.

**Lesson learned (the honest one):** the pipeline mechanics are sound, but the
**fine-tuned CLIP is the weak link** — it called the chair a "lamp" (11%), so the IFC
got the *Lighting* category and the lamp height prior (1.5 m) instead of a chair's
~1.05 m. Geometry is only as trustworthy as the label feeding the IFC. This is the
same "detection is the weak link" finding from `docs/FINDINGS.md` #1, now reproduced
end-to-end: the next real quality lever is a better office-object classifier, not more
mesh post-processing.

## Change 14 — THE big one: a state-dict remap was loading the image encoder with random weights

**File:** `backend/triposr/tsr/system.py` (+ `_tsr_state_dict_remap.py`)
**Severity:** critical — silently corrupted **every** TripoSR reconstruction since 2026-06-10.

**Symptom:** every photo (chair, hamburger, anything) reconstructed as a spiky,
fragmented blob — thousands of disconnected components, unrecognisable. Post-processing,
segmentation, smoothing, and input quality were all ruled out by experiment (old code,
frame-filling demos, and correct masks all still blobbed).

**Root cause:** the `SCS PATCH (2026-06-10)` in `system.py` ran `remap_tsr_state_dict`
**unconditionally**, on the assumption that transformers 5.x renamed the ViT keys from
the legacy `encoder.layer.N.attention.attention.query` to `layers.N.attention.q_proj`.
But the installed **transformers 5.5.4 keeps the LEGACY naming** for this ViT. So:

```
model expects:        image_tokenizer.model.encoder.layer.0.attention.attention.query.weight  (legacy)
RAW checkpoint load:  missing=0   unexpected=0     ← perfect
REMAPPED (old code):  missing=192 unexpected=192   ← 192 image-encoder tensors never loaded
```

`load_state_dict(strict=False)` swallowed the mismatch, so **192 image-tokenizer tensors
kept their random init**. A randomly-initialised image encoder emits meaningless features
→ a meaningless density field → spiky garbage, deterministically, for every input.

**Why "the April 28 version worked":** April 28 predates the June-10 remap shim entirely,
so it loaded the weights raw (0 missing) and reconstructed cleanly. The regression was the
patch, not the model, the marching-cubes swap, or the inputs.

**Fix:** auto-detect instead of remapping blind — `load_state_dict` raw first, and only
apply the legacy→5.x remap if the raw load actually misses `image_tokenizer` keys. After
the fix, chair.png reconstructs as **one clean solid component (seat + back + 4 legs)**
vs. 1,297 fragments before.

**Lessons learned:**
1. **`strict=False` on `load_state_dict` is a silent footgun.** It will happily leave a
   whole sub-network on random weights and never raise. Always assert
   `len(missing_keys) == 0` (or log + fail) for weights you *know* must load.
2. **Don't translate weights on an assumption about a library version — verify against the
   actual model.** A two-line `load_state_dict(raw)` probe (missing=0?) would have caught
   this on day one. Auto-detect beats a hard-coded version assumption.
3. **Garbage output far downstream (a blobby mesh) can trace all the way back to weight
   loading.** We chased post-processing, segmentation, and inputs first; the real cause was
   the very first step. Check that the model loaded correctly before blaming the algorithm.
4. The user's "an old version worked" memory was the highest-signal clue — a working
   reference point bisects the regression faster than any forward debugging.
