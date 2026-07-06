# IFC Optimizer — what it does & how it's wired into the app

**Status: already integrated and automatic. No separate step, no further work needed.**

When you click **“📥 Download all as one IFC”** in the app, the optimizer runs automatically as part
of that same action. It is *not* a separate button, tab, or manual step.

---

## 1. What it does — `backend/python-scripts/optimize_ifc.py`

Three passes over the exported IFC, then an optional zip:

1. **Clean geometry** — the shared `clean_mesh()` (debris/spike removal → MeshFix watertight repair →
   Taubin smoothing → quadric decimation). Each **unique** mesh is cleaned **once** (cached by geometry
   hash), never re-cleaned per instance.
2. **Instance** — identical furniture meshes are stored **once** and referenced N times (geometry-hash
   dedupe + reference re-pointing), so repeated objects don't bloat the file.
3. **Precision** — `CoordList` coordinates rounded to 4 decimals (~0.1 mm) → smaller STEP text.
4. *(optional)* **Zip** — gzip to an `.ifcZIP`-style file.

It writes an optimized `.ifc` plus a before/after report:
`faces_reduction_pct`, `size_reduction_pct`, `unique_meshes`, `meshes_instanced_away`,
before/after `{products, face_sets, faces, vertices, kb}`.

---

## 2. How it's wired into the app (automatic)

| Layer | File | Behaviour |
|---|---|---|
| Export route | `backend/routes/exportRoutes.js:123` | After building the IFC, **auto-runs** `runOptimizeIFC()` — unless the request sends `optimize: false`. On success it swaps in the optimized file and attaches the report. |
| Runner | `backend/routes/exportRoutes.js:17` (`runOptimizeIFC`) | Spawns `optimize_ifc.py` on the pinned Python interpreter. |
| Frontend confirm | `frontend/js/exporter.js:74` | Shows a toast: **“✓ IFC exported + optimized — X% fewer faces, Y% smaller file.”** |

So the flow is: **Download all as one IFC → build IFC → optimize IFC → download the optimized file**,
all in one click.

### Measured results (examples)
- Office chair: **17,544 → 15,000 faces**, **548 → 424 KB** (−14.5% faces, −22.6% size) on top of the
  graft's own decimation.
- Earlier furniture: up to **−82.5% faces / −85% size** where geometry instancing applied.

---

## 3. What the user sees / how to control it

- **Sees:** only the **post-export toast** confirming optimization. There is **no upfront label** in
  Step 4 describing it (functionally complete, just not advertised).
- **Disable per request:** send `optimize: false` in the `/export/ifc` body (default is on).

### Optional polish (not required)
A one-line note could be added under the export button, e.g.
*“Auto-optimized — smaller, cleaner IFC (fewer faces, instanced geometry).”*
This is cosmetic only; the optimization already runs regardless.

---

## 4. Bottom line

- **Integrated:** yes — in the export route, automatic on every IFC download.
- **Separate step needed:** no.
- **Further work needed:** none for it to function. The only optional item is a visible UI label so
  end users *know* it happens (currently confirmed only by the toast after export).
