# Late-Category Variants — sourcing, screening, double-tested coverage

**Problem (user, 2026-07-15):** the 15 categories added late in the project
(presentation kit + tier-2 office realism) had ZERO selectable catalog
variants — the ⋯ browser showed only the built-in primitive.

**Delivered: 44 clean variants, every category ≥2 selectable, double-tested.**

## Sourcing — strict identical-item rule

Only the 15 categories in question; every mesh must BE the item (no loose
matches, no new categories — the upload API validates names against the
catalog enum).

| Source | Count | License | Notes |
|---|---:|---|---|
| PolyHaven | 6 | CC0 | fire extinguisher, first-aid box, projector (vintage film), folding-screen partition, tripod projection screen, microwave (vintage) |
| Parametric (ours) | 38 | ours | 2–3 recognizable styles per category, colored PBR parts, engine tag PRIM |

**Rejected during screening** (identical-item rule): `standing_chalkboard_01`
(a signage board, not a flipchart) and `worn_metal_rack` (shelving, not a
server rack). ABO was checked first: the full Amazon Berkeley Objects set has
**no 3D models** for any of these 15 product types.

All 44 registered through the real upload pipeline: professional codes
(`whiteboard-PRIM-001`, `microwave-CC0-001`, …), auto-thumbnails, renumbering
on delete. Coverage after: 14 categories × 3 variants, server_rack × 2.

## Double test (2× full runs, 40/40 checks PASS)

`scripts/test_late_variants.py` forces the NEW meshes through the real
variant-selection path (`items[].ids` in rooms, `gen:<id>` picks in
buildings) and asserts the Item Logic Register rules:

- **Presentation 10×8**: 26 placed, projector CEILING 2.2 m with
  `throws_onto` the CC0 tripod screen, chair rows centred on the display
  axis, zero exact-polygon overlaps.
- **Office 8×6**: 23 placed — partitions (incl. the CC0 folding screen),
  floor-MFP printer, server rack flush at the wall (0.55 m), planters at
  corner/wall, zero overlaps.
- **Kitchen 5×4**: the CC0 vintage microwave ON the table (elev 0.74,
  `on_top` link) beside the espresso machine; zero overlaps.
- **Break 6×5**: PRIM microwave + pod machine ON the table; zero overlaps.
- **Building (Bürogebäude, real IFC)**: office picked with `gen:` ids —
  all variants placed, extinguisher mounted at **1.00 m**, first-aid at
  **1.35 m**, human links recorded (`in_front_of`, `beside`, `on_top_of`,
  `door_flank`), clash counter **0**.

Reproduce: `python scripts/test_late_variants.py` (run twice for the
double-test discipline). Sourcing is reproducible via
`scripts/fetch_ph_variants.py` + `scripts/make_prim_variants.py`.
