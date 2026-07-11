# TripoSR Repair-Pack Benchmark — Single-Image A/B Proof (2026-07-11)

**What this is:** the standalone proof that the archetype repair packs
(`backend/python-scripts/repair_packs.py`) significantly improve TripoSR output —
and the quality of the exported IFC — for **all 17 furniture categories** in the
app's picker, WITHOUT changing the app. 10 gallery "lists" × 17 items, each item:
one internet photo (never from the catalog) → the mesh TripoSR ships today → the
same mesh after repair. 170 unique photos, all CLIP-validated, all timestamped.

**Campaign:** 2026-07-11 05:13 → 08:00 local · 170/170 generated, 0 failures ·
RTX 4050 Laptop 6 GB · TripoSR loaded once, ~55 s/item.

## View the results

```bash
cd benchmark
python -m http.server 8000        # separate from the app on :3000
```

| Page | What it shows |
|---|---|
| `http://localhost:8000/` | index — campaign window, aggregate metrics table, links |
| `list01.html` … `list10.html` | 17 rows each: photo \| TripoSR today \| repair packs, with per-item metrics + timestamps + source links |
| **`visualizer.html`** | 🎛 **candidate visualizer** — every mesh variant of an item side by side in interactive 3D (orbit/zoom/pan); click **Select** to record the winner; ⬇ exports `selections.json`. Any extra `<variant>.glb` dropped into an item's results folder (e.g. `triposg.glb`) appears automatically after re-running `build_candidates.py` |
| `angles.html` | 📸 per-category photo-angle capture guide |

## Headline numbers (170 items)

| Metric | TripoSR today | Repair packs |
|---|---|---|
| Mean faces | 111,143 | 12,039 (9.2× lighter) |
| Watertight solids | fragments individually closed | 91% fully closed objects |
| Broken bases rebuilt | shipped broken | 48 (evidence-driven: legs at detected stub positions / tripod / trestle / pedestal / plinth) |
| Silhouette IoU vs photo | 0.662 | 0.646 (shape preserved while restructuring) |
| IFC spot-proofs | — | 20/20 valid IFC4 with real mesh geometry (`saveIFC.py`, the app's exporter) |

Honest notes: where the photo is a clean single object, the improvement is obvious
(office chairs, stools, clocks, cabinets). Angled/cluttered museum-style shots
produce blobby bodies — the repair fixes their *structure* (solid, grounded,
light, IFC-valid) but cannot invent detail the single view never contained.
Known v3 candidates: gentle auto-level for tilted items, sofa blockiness.

## The repair packs (what runs per category)

Every CLIP label / picker category resolves to one of 7 repair archetypes; each
runs a hand-picked stack of 8 guarded CPU stages (a failing stage falls back):

| Archetype | Categories | Signature fixes |
|---|---|---|
| legged | table, desk, coffee/side table, stool, chair, bench | strict symmetry, **support health check → evidence-driven rebuild** |
| swivel_seat | office_chair | drift removal + the proven 5-star base graft |
| boxy | cabinet, filing_cabinet, bookshelf, wardrobe, dresser | crisp-edge smoothing, plinth rebuild |
| upholstered | sofa, couch, armchair, bed | Taubin×14 fabric softness, plinth |
| panel | mirror, picture_frame, clock, monitor, tv | tanh thickness clamp — flat wall slabs |
| slender | lamp, planter, plant | thin-part-protecting filters, no forced symmetry |
| prop | laptop + anything unknown | safe universal clean (the fallback for any object) |

Universal stages: up-aware debris filter (keeps legs/poles) → per-component
pymeshfix → detected-plane symmetry snap (axis+offset chamfer-scored — no X=0
assumption) → Taubin smooth → decimate to 10–15k → panel flatten → final
crumb-sweep + watertight heal → support rebuild (only when the bottom is broken;
an intact tripod/pedestal always passes the health check) → flush floor contact.

Env knobs: `SCS_REPAIR_PACKS=0` (kill-switch), `SCS_REPAIR_ARCHETYPE=<name>`
(force, e.g. the office-chair UI toggle), `SCS_REPAIR_UP_AXIS` (default 0 = X;
TripoSR's native frame is X-up — verified empirically).

## Rerun / extend

```bash
python fetch_images.py            # top up photos (Openverse + Commons thumbnails/categories)
python validate_images.py         # CLIP-screen photos; purge+refill; renumber (two-phase, safe)
python batch_generate.py --lists 1-10   # cached: only missing/changed items regenerate
python build_gallery.py           # rebuild the list pages + index
python build_candidates.py        # re-index mesh variants for the visualizer
```

- Per-item outputs: `results/listNN/<category>/{raw.glb, improved.glb, raw.png,
  improved.png, metrics.json[, item.ifc]}` — metrics carry exact timestamps.
- Photo provenance: `images/sources.json` (URL, source, fetch time per photo).
- To A/B a NEW generator: drop its mesh as `results/listNN/<cat>/<name>.glb`,
  re-run `build_candidates.py`, and pick winners in the visualizer.

## Engineering notes (bugs found by this benchmark, already fixed)

1. **Axis swap in support building** — legs built in local Z-up then rotated
   landed 90°-off in plan; the builder now works directly in world coordinates.
2. **Decimation opens cracks; the support cut opens the body** — a final
   `_finalize` stage (crumb sweep + fill_holes + per-component pymeshfix) restores
   watertightness; the cut body is healed inside the rebuild.
3. **Internet photos need semantic screening** — CLIP validation of every photo
   (subject present, not a room/painting/person), with curated Wikimedia
   `Category:` listings as the refill source for sparse types.
4. **Wikimedia throttles bulk full-res downloads** — use `iiurlwidth=1024`
   thumbnail URLs.
5. **CLIP on flat single-color renders is unreliable** (calls everything a stool)
   — kept per-row as an honest "render reads as" note, excluded from headline metrics.
