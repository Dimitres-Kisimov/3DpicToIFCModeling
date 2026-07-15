# SCS Studio v2.0.0 — patch notes (2026-07-15)

v1.0.0 → v2.0.0, everything user-driven, everything gate-tested. Author:
Dimitres Kisimov.

## New feature: 90° object rotation (yaw-only)

Select any placed piece in the **Building** workspace — 3D view or 2D floor
plan — and rotate it with the **⟳ 90° button or the R key**. Strictly a turn
around the vertical axis in 90° steps: a chair can face the four walls and
nothing else — tilting toward ceiling or floor is structurally impossible
(no other rotation axis is ever written). The 2D and 3D views share one
state, legality is re-checked on every turn (an illegal rotation snaps
back), and the rotation is **baked into 💾 Save layout (GLB) and the IFC
export** — verified end-to-end: a 2.0×0.9 m sofa rotated 90° leaves the
export with swapped footprint axes and untouched height. *Build a room* had
rotation already (R / ⟳ in the 2D plan editor, scene rebuilds in 3D).

## New placement rules (the Item Logic Register grew)

- **Safety access (ASR — "very important")**: fire extinguisher and
  first-aid cabinet own their wall spot (1.00 m / 1.35 m grip heights) AND a
  hard 0.90 m keep-out strip in front — no bookshelf can block them at any
  density, in rooms and buildings alike.
- **Armchair rows (user rule)**: armchairs arrange like humans use them —
  two side by side facing the same way; four as two opposed pairs facing
  each other; the side table sits with them and carries the cluster's plant
  (`planter on_top side_table`, capped at one so corner planters stay
  corner planters). The row block goes wherever a legal gap exists — the
  solver's clearances keep it off the walkways.
- **Meeting rooms**: a real rule pack at last — every seat rings the table
  FACING it (the "chairs turned the other direction" bug); leftover seats in
  buildings join the nearest real table's ring instead of drifting.
- **Kitchens**: fridge + microwave belong here; the microwave (and coffee
  machine) ride ON the table — never the floor.
- **Dependency realism**: service items exist FOR the furniture they serve —
  a room that ends up with no work/dining surface keeps at most one waste
  bin and zero partitions ("why so many dustbins" bug).

## Catalog

- **44 screened variants** for the 15 late categories (6 PolyHaven CC0 + 38
  parametric PRIM styles), every category ≥2 selectable options, strict
  identical-item screening (2 candidates rejected), colors verified in the
  GLBs, engine badges CC0/PRIM.

## Showcase & docs

- Human-Layouts showcase rebuilt as **11 realistic room scenarios** — four
  real office types (duo cell, team, executive, open plan) + meeting,
  presentation, break, kitchen, reception, quiet, living control.
- Item Logic Register (in-app tables + repo MD + local Word) with the
  German-standard verdict per item; presentation shot pack + per-building
  X-ray pictures for slides; tab deep-links (`/#room`, `/#building`).

## Gates at v2

density×ASR monotonicity + legal-cap sweep · late-variant ergonomics 40/40
(re-run post-changes) · 11 scenarios re-rendered through the live solver ·
fleet re-populated with exact-meter check · rotation bake verified in
GLB export · full JS/Python compile sweep.
