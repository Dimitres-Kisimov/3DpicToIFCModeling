# Part 2 — Full-Proof Ergonomics Engine + One App

Branch target: continue on a Part-2 feature branch (not `main`).

## Context

Part 1 (photo→3D generator + office-chair base graft + IFC optimizer) is done. The executive's
remaining review items are about **furnishing whole rooms correctly**:

- #4 chair behind desk, lamp on desk (relationships)
- #5 no chairs facing / colliding with walls; leave room for **people to move**
- #6 a **2D floor-plan** where a person can manually move furniture
- #3 catalog: preview + title newly-added images *(deferred — later phase)*

The user's sharpening: the rules must be **robust and object-agnostic** ("think for every object"),
with **human clearances** ("distance behind the chair, around a table for a person to move, imagine
there are people — we need space"), and **no random material standing**. Selection is **space-gated**:
the user picks objects; if they fit they're placed, else **"not enough space"** — with an *optional*
"furnish as the algorithm sees fit" mode.

**Non-negotiable cross-cutting requirements:**
- **ONE professional, deployment-ready app** — the 2D→IFC room builder and the photo→3D generator
  become a single product, not two servers/UIs.
- **2D is the manual authoritative surface:** the user drags each object to its **exact** location in
  2D; the **3D updates live** to match and **re-validates** (collision/clearance). Collisions include
  the **building model's own fixed elements** (pillars/columns, walls, beams — see A3b).
- **Every manually-added catalog item gets a 3D preview** (thumbnail + interactive).
- **Efficiency is a hard requirement:** must **not crash the PC**, must **minimize processing**, and
  must choose **GPU vs CPU per task** — GPU only where it is genuinely faster/safer (see Workstream D).

### Key discovery — most of the "room builder" already exists (port 8000)

`backend/app_server.py` (Flask, :8000) + `demo/app.html`/`demo/app.js` already provide: catalog
selection (steppers + specific-mesh picker), a **space/feasibility check** (`spatial_layout.py`
CP-SAT → `infeasible-overpacked` → "Doesn't fit" message), **both room sources** (user-defined
`W×D×type`, and the loaded `Duplex_Architecture.ifc` via `populate_building.py`), and drag-to-
reposition. The layout engine (`spatial_layout.py`, `rule_packs.py`, `build_room_scene.py`) is solid
but **item-centric, not people-centric**.

**So Part 2 = harden the engine + merge :8000 into :3000 + add a 2D editor.** Scope chosen:
ergonomics engine + 2D editor (catalog previews deferred).

---

## Workstream A — Object-agnostic, people-aware ergonomics engine

Extends `spatial_layout.py` + `rule_packs.py` + `build_room_scene.py`. Reuses the CP-SAT solver,
anchoring, and clearance tables; adds the missing human/interaction layer.

### A1. Placement archetypes (covers ALL objects, not a per-item list)
Add an `ARCHETYPES` map in `rule_packs.py`: every category resolves to one archetype (unknown →
footprint-derived default). Each archetype defines **directional interaction zones** sized from the
object's real dimensions + human constants — so new/unknown objects still get correct behavior.

| Archetype | Members (examples) | Interaction zone (human clearance) | Facing / wall |
|---|---|---|---|
| `worksurface` | desk, table, conf/coffee/side table | **approach+legroom** on user side(s), 0.60–0.75 m deep | user side faces open floor |
| `seating` | chair, office_chair, armchair, sofa, stool, bench | **pull-out/stand-up** behind, 0.45–0.60 m; faces its paired surface / focal point | faces anchor, never a wall |
| `storage_access` | cabinet, filing_cabinet, wardrobe, bookshelf, shelf | **door/drawer swing + access** front, 0.60–0.90 m | back to wall (wall-affine) |
| `bed` | bed | **access** both long sides + foot, 0.60–0.70 m | headboard to wall |
| `appliance` | fridge, oven, microwave, sink, toilet, bath | **approach/door** front, 0.60–1.00 m | access side to room |
| `on_surface` | monitor, laptop, lamp(desk), keyboard, book, vase, clock | none (sits on parent) — anchored `on_top` | — |
| `wall_mounted` | mirror, picture_frame, tv, wall clock | viewing stand-off; no floor footprint | on wall |
| `free_accent` | floor lamp, planter | small footprint buffer; kept out of aisles | free |

Human constants (new `ANTHRO` block in `rule_packs.py`, sourced from the ADA/Neufert values already
cited): person shoulder ≈ 0.55 m, walking aisle ≥ 0.90 m, seated pull-out ≈ 0.55 m, turning circle
1.525 m. These drive zone depths so the rules are *derived*, not hand-tuned per object.

### A2. Interaction zones as first-class solver inputs
Today the solver only knows footprint + a scalar clearance buffer. Extend
`spatial_layout._solve_layout_ortools` so each object contributes, in addition to its footprint:
- its **directional interaction zone(s)** as *reserved rectangles* that no other footprint may occupy;
- these rotate with the object (so a rotated desk's legroom moves with it).

Reuse the existing `AddNoOverlap2D` machinery — interaction zones are added as extra non-overlappable
rectangles bound to the parent's position/rotation. Extend rotation from 0/90° to **0/90/180/270°**
so facing can be satisfied.

### A3. Circulation guarantee (people can move — hard constraint)
After a candidate placement, enforce a **walkable network**:
1. Rasterize the room free space (reuse the 10 cm grid); inflate every footprint **and every
   building obstacle** by half a person width.
2. Require a **connected free path** (flood-fill / BFS on the grid) from **each door** to **every
   object's access/interaction zone**, at ≥ `min_aisle` width (`rule_packs` already defines it —
   now *enforced*).
3. If a placement disconnects the network, it's infeasible → reported (see A4).

This directly delivers "around a table, distance for a person to move" and "no chairs facing the wall"
(a chair whose front is against a wall has an unreachable seat → rejected).

### A3b. Building-model obstacles are first-class collision objects
Everything fixed that comes **from the loaded building IFC** — **pillars/columns, walls, beams,
door swings, and any pre-existing fixed elements** — is extracted as a hard keep-out and respected by
BOTH the auto-layout solver and the manual 2D editor (C). This already exists partially:
`populate_building.footprint_rects()` / obstacle extraction pulls `IfcColumn`, walls, and door zones
from the Duplex IFC. We **generalize** it into a single `extract_room_obstacles(ifc, space)` used
everywhere, covering `IfcColumn`, `IfcBeam` (projected), `IfcWall`/partitions, `IfcStair`, and any
`IfcBuildingElement`/existing furniture in that space — returned as labeled rectangles (`kind`:
column/beam/wall/existing). Furniture may never overlap them; circulation must route around them.

### A4. Space-gated selection + honest failure ("not enough space", no random dumping)
Replace the current partial-place-and-flag behavior with a clean gate:
- The solver either **places every selected item** with full footprint + interaction zones +
  circulation, or returns **infeasible** with **per-item diagnostics**: which items couldn't be
  placed, approximate area shortfall, and a suggestion (*remove item X, shrink it, or enlarge the
  room by ~N m²*).
- **Never** place an item without its required clearances/facing (kills "random material standing").
- Frontend surfaces this as the existing red "not enough space" message, upgraded with the per-item
  detail.

### A5. Optional "auto-furnish as the algorithm sees fit"
A non-default mode: given room + type, propose a sensible set from `rule_packs` suggestions capped by
Neufert **area/person**, then arrange via A1–A4. Reuses `populate_building.smart_furnish`.

### A6. Generalized facing + persist relationships
- Generalize `build_room_scene._chair_forward_xz` into a per-archetype **front-vector** resolver
  (seating faces anchor/focal; storage/appliance faces access-side into room; worksurface user-side
  to open floor).
- Persist functional groups (chair-with-desk, monitor-on-desk) into the IFC (`IfcRelAggregates` /
  Pset) in `build_room_ifc.py` so downstream/building population stays coherent (currently dropped).

**Files touched:** `rule_packs.py` (archetypes, anthro, zone math), `spatial_layout.py` (zones as
rectangles, circulation check, richer infeasible report), `build_room_scene.py` (facing, zone wiring),
`build_room_ifc.py` (relationship persistence). All additive — the existing single-room and
`populate_building` callers keep working.

---

## Workstream B — One app (merge :8000 room-builder into :3000)

Goal: a single server + single UI. The room logic is Python invoked by Flask today; the :3000 app is
Node already invoking Python via a subprocess bridge — so we make **Node the single front door** and
retire Flask.

- **B1. Node routes replace Flask endpoints.** Re-implement `app_server.py`'s ~12 endpoints
  (`/api/catalog`, `/api/items/:cat`, `/api/generate` layout, `/api/buildings`,
  `/api/building/:id/rooms`, `/api/building/:id/populate`, `/api/building/:id/save`,
  `/api/upload_generated`, thumbnails, `/out/:p`) as Express routes that spawn the **same, unchanged**
  Python scripts (`catalog.py`, `build_room_scene.py`, `populate_building.py`). Pattern already used
  for generation/export.
- **B2. Unified UI.** Fold `demo/app.html`/`app.js` into the :3000 frontend as a **"Build a room"**
  section/tab alongside the existing **"Generate an object"** flow; share one xeokit viewport, one
  catalog, one IFC export + the Part-1 IFC optimizer.
- **B3. Close the loop.** Objects generated on the photo→3D side auto-register into
  `data/generated_assets/manifest.json` so they appear in the room picker immediately (today it needs
  manual re-upload). This is the real payoff of one app.
- **B4. Retire Flask/:8000** and the dual-start scripts; one `node backend/server.js` runs everything.

---

## Workstream C — 2D floor-plan editor with live 3D sync (boss #6)

The 2D plan is the **authoritative manual-placement surface**; 3D mirrors it. Top-down view in the
merged app (SVG or 2D canvas — vanilla, matching the codebase):

- **Draws the true room** — rectangle or the real `IfcSpace` polygon, plus **all building obstacles
  from A3b** (pillars/columns, walls, beams) as solid keep-outs, doors, and each furniture
  **footprint** with its **interaction zone** halo and shaded **circulation aisles**.
- **Manual, exact placement.** Drag an object to its precise spot; type exact X/Y coordinates and
  rotation for pixel-accurate positioning; optional grid snap toggle.
- **Live collision + clearance while dragging.** Continuously test the dragged footprint against
  (a) other furniture, (b) **building obstacles (pillars/walls/beams)**, (c) interaction zones, and
  (d) circulation. Illegal spots flash red and refuse the drop (or mark it invalid); legal spots
  confirm green. No overlaps are ever committed.
- **2D → 3D live sync + re-validation.** Every move updates the shared object model
  (`id, position, rotation, dims`); the **3D viewer updates immediately** and re-runs the same
  checks, so "the 3D notices the change and fixes it." 3D → 2D also stays in sync if moved in 3D.
- **One model to IFC.** Because both views write the same object model that already flows to
  `/export/ifc` + the Part-1 optimizer, manual edits export correctly as one optimized IFC.

## Workstream C2 — Catalog: manual add with 3D preview (boss #3)

Extend the existing `upload_generated` flow so **every manually-added item gets a 3D preview**:
- On add: store the mesh, **auto-render a cached thumbnail** (server-side, offscreen — see D) and
  register it in `data/generated_assets/manifest.json` with a **title** the user types.
- The catalog picker shows the **thumbnail**; clicking opens an **interactive 3D preview** (reusing
  the xeokit viewer) before it's placed. Thumbnails are rendered **once and cached** — never per view.

---

## Workstream D — Efficiency, resource safety & GPU/CPU strategy (hard requirement)

The app must **not crash the PC** and must **minimize processing**. Task-by-task placement:

| Task | Run on | Why / safeguard |
|---|---|---|
| Photo→3D generation (TripoSR) | **GPU** (RTX 4050 6 GB / prod GEX44) | Only task where GPU clearly wins; **serialize to 1 job** via a queue, free CUDA cache between jobs, cap input size — prevents the 6 GB OOM that crashes the box. |
| Layout solver (CP-SAT), obstacle extraction, IFC read/write, decimation | **CPU** | Fast, light, deterministic; GPU adds nothing. Solver already caps at 30 s; add early-exit on infeasible. |
| Thumbnail / preview render | **CPU offscreen, cached** | Render **once** on add, cache the PNG; never re-render per view. |
| 3D viewing | **client GPU (WebGL)** | Serve **decimated** meshes (Part-1 optimizer, ~10–15 k faces); **lazy-load** per room; dispose off-screen models; never load a whole building at full res. |

Cross-cutting safeguards: a **bounded job queue** (no parallel heavy jobs), **caching** of GLBs +
thumbnails + solver results (hashed by inputs), **streaming** large files, **scratch cleanup**, and a
**graceful degrade** (CP-SAT → grid fallback; GPU-gen → catalog retrieval) so the app never hard-fails.
Add a lightweight `/api/health` resource read (reuse `debug/system`) to watch memory/GPU.

---

## Workstream E — One professional, deployment-ready app

- **Single server, single UI:** Node (:3000) is the only front door (B). One consolidated frontend
  with clear sections — **Generate object · Build room · 2D plan · Export** — sharing one viewer,
  one catalog, one IFC pipeline. Retire Flask/:8000 and the dual-start scripts.
- **Deployment target:** the chosen prod stack (Hetzner GEX44, GPU) — a single `npm start`, env-driven
  config (ports, GPU flag, paths), documented run/build, and a health endpoint. No dev-only demo pages
  in the shipped surface.
- **Robustness:** consistent error handling + user-facing messages (incl. "not enough space"), never
  crashes on bad input, plus the resource safeguards from D.

---

## Phasing (recommended order)

1. **A (ergonomics engine)** — highest value, testable standalone in Python. Archetypes + interaction
   zones + **building-obstacle** collisions + circulation + honest infeasibility.
2. **D (efficiency spine)** — job queue, caching, GPU/CPU split — landed alongside A/B so nothing
   ships that can crash the box.
3. **B + E (one-app merge, deployment-ready)** — room-builder into :3000; single professional UI;
   retire Flask.
4. **C + C2 (2D editor + catalog 3D preview)** — manual exact placement, live 3D sync, previews.
5. *(polish)* IFC relationship persistence, optional auto-furnish mode.

## Verification

- **Python unit tests** (`spatial_layout`): hand-checked rooms — 3×3 m office with 1 desk+chair =
  feasible with a clear aisle; over-pack until infeasible and assert the per-item report; assert a
  chair's seat is always reachable (no facing-wall); assert door→every-access-zone connectivity;
  assert furniture never overlaps a **pillar/wall** obstacle.
- **Both room sources:** user-defined `8×6 office`, and Duplex `IfcSpace` rooms with real columns.
- **2D↔3D:** drag in 2D → 3D reflects the exact position and re-flags collisions incl. building
  obstacles; move in 3D → 2D updates.
- **Efficiency:** run generation + a full building populate while watching memory/GPU — no OOM, one
  GPU job at a time, thumbnails cached (second view = no re-render).
- **End-to-end:** select items → layout → force "not enough space" → 2D drag to fix → export **one
  optimized IFC** that opens in the viewer with furniture correctly spaced, faced, and clash-free.
- **Deployment smoke test:** single `npm start` serves the whole app; Flask no longer required.
- **Regression:** existing `/api/generate` and building populate still succeed.

---

## Phasing (recommended order)

1. **A (ergonomics engine)** — highest value, testable standalone in Python. Ship archetypes +
   interaction zones + circulation + honest infeasibility first.
2. **B (one-app merge)** — bring the room-builder into :3000; retire Flask.
3. **C (2D editor)** — manual override on top of the engine.
4. *(Later)* catalog previews/titles (#3), IFC relationship persistence polish.

## Verification

- **Python unit tests** (`spatial_layout`): hand-checked rooms — e.g. 3×3 m office with 1 desk+chair
  = feasible with a clear aisle; over-pack until infeasible and assert the per-item report; assert a
  chair’s seat is always reachable (no facing-wall); assert door→every-access-zone connectivity.
- **Both room sources:** user-defined `8×6 office`, and Duplex rooms via `populate_building`.
- **End-to-end in the merged app:** select items → layout → force "not enough space" → 2D drag to fix
  → export IFC → confirm one optimized IFC opens in the viewer with furniture correctly spaced/faced.
- **Regression:** existing single-room `/api/generate` and building populate outputs still succeed.
