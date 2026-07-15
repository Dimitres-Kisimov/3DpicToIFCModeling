# Drop Test — "someone throws a 7-storey IFC at the app"

**Question:** if a stranger drags an unknown multi-storey IFC into the *Add a
building* box, does the system recognize every floor and room, and can the
catalog still be used on it?

**Answer: yes — verified twice on 2026-07-15, reproducible with one command.**

```
python scripts/drop_test_7f.py     # server running; self-cleaning
```

## What the test does

1. Synthesizes a **fresh 7-storey tower IFC** the app has never seen
   (12.9 MB, 720 products, 81 spaces, 10 storeys incl. a space-less
   foundation level) — a new file every run, so the upload path is exercised
   cold.
2. Uploads it through the **real endpoint** (`POST /api/buildings/upload`),
   exactly what the drag-and-drop does.
3. Compares the app's answers against ground truth read straight from the
   IFC with ifcopenshell.
4. Retires the test building afterwards — the curated fleet stays untouched.

## Results (run of 2026-07-15)

**Instant profile on upload** (before any scan): 10 storeys, 81 spaces,
720 products, schema IFC2X3, honest populate-time estimate — all correct.

**Floor dissection** — every space-bearing floor, exact room counts:

| Floor | IFC ground truth | App documents |
|---|---:|---:|
| Level 1 | 10 spaces | 10 rooms ✓ |
| Level 2 | 10 spaces | 10 rooms ✓ |
| Tower Level +1 … +6 | 10 spaces each | 10 rooms each ✓ |
| Roof | 1 space | 1 room ✓ |

**9/9 space-bearing floors, 81/81 rooms, zero mismatches.** 32 rooms carried
smart furniture suggestions immediately. The foundation storey (no spaces)
is profiled but correctly not offered as a furnishable floor.

Two independent runs both passed: the first on a cold cache (~10 min,
dominated by the one-time geometry scan every new building pays once), the
second warm (**25 s** end to end).

## Catalog on an uploaded building

Uploaded buildings use the same global catalog as everything else — verified
by populating an uploaded IFC with explicit picks:

```
picks = {"living room": ["sofa", "coffee_table", "planter", "gen:gen_93b581b6d4f7"]}
```

Result: `sofa-0, coffee_table-1, planter-2, table-3` placed — the last one
being **our own AI-generated item (table-TSR-008)**. Categories, ABO meshes
and user-generated items are all pickable per room on any dropped building;
generated items are addressed as `gen:<id>` (the Building tab's selection
bar does this automatically).

## Prior evidence

- `backend/python-scripts/test_floor_dissection.py` — 15/15 fleet buildings
  vs IFC ground truth.
- The entire curated fleet (NBU, 210 King, Bürogebäude…) originally entered
  the app through this same upload path.
