# 3DpicToIFC — Stage A Release Notes

- **Version:** 0.9.0-stageA (interim zip distribution; Electron .exe planned)
- **Date:** 2026-07-12
- **Platform:** Windows 10/11, 64-bit

## Highlights

- **Photo → 3D → IFC in one app** — upload a furniture photo, get a
  cleaned, real-world-scaled 3D model (GLB) and a BIM-ready IFC file, with
  automatic detection and classification across **17 furniture categories**
  (desks, office chairs, sofas, cabinets, bookshelves, lamps, monitors, …).
- **Repair packs** — automatic mesh repair for generated models: hole
  filling, debris removal, smoothing, decimation, and the office-chair
  5-star base graft.
- **Room builder** — compose rooms from the bundled furniture catalog plus
  your own generated objects; auto-layout with human-sense placement rules;
  colored 3D preview and one-click room IFC export.
- **Building population** — load an architectural IFC (a sample Duplex is
  included, or upload your own) and populate its rooms with furniture,
  exporting a fully furnished building IFC.
- **Runs fully local** — Node.js server + Python AI pipeline on your PC;
  photos and models never leave your machine.

## Known limitations (Stage A)

- **Zip + batch-file install**, not a signed one-click installer yet;
  Node.js and Python must be installed first (setup.bat guides you).
- **Large first-time downloads**: setup pulls several GB of Python/AI
  libraries; the first 3D generation downloads model weights (a few GB,
  one time) and needs internet.
- **Starter catalog only**: a small subset of the full ~4.8 GB furniture
  library is bundled. Catalog items without a bundled mesh appear as
  correctly-sized simple shapes.
- **GPU strongly recommended**: NVIDIA 6 GB+ for fast generation; the CPU
  fallback works but high-quality generation can take several minutes per
  photo.
- Single-user, single-machine: the app binds to `localhost:3000` and
  processes one GPU job at a time.
- Photo → 3D quality depends on the input: one object per photo, plain
  background, and good lighting give the best results.
