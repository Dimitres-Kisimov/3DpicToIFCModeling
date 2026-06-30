# Photo → 3D accuracy — methodology & results

The paper's first part claims a 2D photo can be turned into an accurate 3D model.
This is how we *measure* that claim, and the numbers we have so far.

## Why we can measure it cleanly (ABO-as-ground-truth)
We own **400 real product meshes** (Amazon Berkeley Objects, CC-BY-4.0). So we render a
mesh to a synthetic photo, reconstruct it with a generator, and compare the result back
to the **known original**. Most photo→3D papers lack ground truth; we have 400.

## Metric (`backend/python-scripts/eval_accuracy.py`)
Both meshes are centred and scaled to unit bounding-box diagonal, then the reconstruction
is aligned to the ground truth with **multi-seed ICP** (12 seed rotations × ICP, keep best —
reconstructions come out in an arbitrary canonical frame). Then we sample surface points and compute:

- **Chamfer distance** — mean bidirectional nearest-neighbour distance (lower = better)
- **F-score @ τ=0.02** — precision/recall of points within τ of the other surface (higher = better)
- **precision** = reconstruction near GT; **recall** = GT covered by reconstruction

Sampling is **seeded → reproducible**. Validated by `--selftest`: identity F=1.00,
noisy-1% F=0.99, decimated-20× F=1.00, *different object* F=0.18 (monotone, discriminating).

## Result so far — TripoSR baseline (single image, local RTX 4050)
End-to-end `eval_photo3d.py` (render → TripoSR → score), 3 office chairs:

| object | chamfer | F@0.02 | precision | recall | sec |
|--------|---------|--------|-----------|--------|-----|
| chair B07DBH52YB | 0.168 | 0.227 | 0.72 | 0.14 | 23 |
| chair B076HDDMKM | 0.165 | 0.087 | 0.88 | 0.05 | 13 |
| chair B075ZZYH4B | 0.175 | 0.151 | 0.84 | 0.08 | 12 |
| **mean** | **0.169** | **0.155** | **~0.81** | **~0.09** | |

**Key finding — the single-view ceiling, quantified:** precision is high (~0.81) but recall
is low (~0.09). TripoSR reconstructs the *visible* surface fairly accurately but recovers
only ~9% of the true surface — it cannot see the back/sides of the object from one photo.
For context, the metric's "different chair" baseline is F=0.18, so a single-view recon of
the *correct* chair is in the same ballpark as a *wrong* chair on coverage — usable for
client visualisation, not BIM-grade geometry. This matches the project's prior findings.

## Scaling to the 4-way bake-off (cloud)
The same metric scores all four generators (`backend/python-scripts/eval_bakeoff.py`):

1. **Render GT photos + manifest:**
   `python eval_bakeoff.py photos --categories office_chair,desk,table --n 5`
   → `bakeoff_in/photos/*.png` + `manifest.json` (object_id → GT mesh).
2. **Generate on RunPod** (A40, ~$10): upload `bakeoff_in/`, run per photo with GT scoring:
   `bash cloud/compare_4way.sh photo.png gt.glb` — runs TripoSR / InstantMesh / TRELLIS /
   SAM 3D and writes Chamfer/F-score per model (same `eval_accuracy.py`) into the report.
3. **Aggregate:** `python eval_bakeoff.py score --recons <downloaded> --manifest manifest.json`
   → `comparison.md` + `comparison_accuracy.png` (model × chamfer/F-score).

## Honest interpretation for the paper
- Getting *a* mesh from a photo: solved (TripoSR, ~15 s/object).
- Getting an *accurate* (full-surface, metric) mesh from **one** photo: capped by the
  single-view ceiling above. The route past it is **multi-view** + **scale calibration**
  (next checkpoints), not a better single-image model.
- IFC/BIM compliance rides on detection + dimensions, not mesh fidelity — so the product
  goal is more tractable than perfect geometry.
