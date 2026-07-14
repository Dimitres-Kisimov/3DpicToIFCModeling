# SCS Studio — Developer & Functionality Manual

**The complete map: what every functionality is, where it lives, how it works, and how to
extend it.** Written for whoever maintains or expands this app after the current project.
PDF copy: `deliverable/DEVELOPER_MANUAL.pdf`. Last verified against the running app on
2026-07-14 (end-user suite 8/8, floor dissection 15/15).

---

## 1. Run it

```bash
npm install                      # Node deps (Express, xeokit)
pip install -r requirements.txt  # + the pip line in README Quick start
npm start                        # -> http://localhost:3000
```

One Node server (`backend/server.js`) serves everything: the app, the research hub, all
static evidence, and the REST API. Python does all heavy work in per-request subprocesses —
**Python file changes need no server restart; Node file changes do.**

Two permanent test gates (run them after ANY change — user directive):

```bash
python backend/python-scripts/test_e2e_smoke.py         # 8 end-user capabilities
python backend/python-scripts/test_floor_dissection.py  # every building vs IFC ground truth
```

---

## 2. Where every functionality lives

| Functionality | Frontend | Backend route | Python |
|---|---|---|---|
| Photo → 3D generation | `frontend/js/index.js`, `api.js` | `routes/apiRoutes.js` `/api/generate` | `run_triposr.py`, `_triposr_postprocess.py`, `inference_base.py` |
| Chair base menu (6 styles + Auto) | `index.html` `#baseStyleSel` | same route (`baseStyle`) | `graft_chair_base.py` |
| Segmentation (rembg default, SAM2 opt-in) | — | — | `run_triposr.py` (`SCS_TRIPOSR_SEGMENTER`) |
| Catalog (38 categories + custom) | `js/roomBuilder.js` | `routes/roomRoutes.js` `/api/room/catalog` | `catalog.py` |
| Professional numbering (item–AI–NNN) | both pickers show `code` | delete/upload hooks | `room_api.py` `renumber_generated_catalog()` |
| Custom category + IFC item upload | roomBuilder "＋ New category…" | `POST /api/room/catalog/custom` | `room_api.py` `cmd_register_ifc_item` |
| Delete catalog item (✕, compacts numbering) | roomBuilder `gen-del` | `DELETE /api/room/generated/:gid` | `room_api.py` `cmd_delete_generated` |
| Room solver (ergonomics) | `js/roomBuilder.js` | `/api/room/layout` | `spatial_layout.py` (CP-SAT), `rule_packs.py` |
| Rule packs: Neufert/Panero/ADA + **ASR** | — | — | `rule_packs.py` (`ASR`, `get_pack`, `placement_profile`) |
| Building registry + upload | `js/buildingMode.js` | `routes/buildingRoutes.js` | `room_api.py` probe cmds |
| Building rooms/floors | room cards + floor chips | `/api/building/:bid/rooms` | `room_api.py` `cmd_building_rooms` |
| Building populate (density, picks) | density chips + room cards | `POST /api/building/:bid/populate` | `populate_building.py` |
| Presentation-room ROW ENGINE | — | — | `populate_building.py` (search "3c) PRESENTATION") |
| Walking-path protection | — | — | `populate_building.py` `extract_room_obstacles` + edge-gap scan |
| Rotated-building handling (theta) | `js/buildingMode.js` `toLocal/toWorld` | rooms payload `theta` | `detect_building_theta`, de-rotated solve frame |
| 2D floor plan editor | `js/buildingPlan.js`, `planEditor.js` | — | zones/obstacles from rooms payload |
| Clash engine + Resolve | `js/buildingMode.js` (`isLegalPiece`) | — | solver guarantees at populate time |
| IFC export + optimizer | export buttons | `/api/export/ifc`, building save | `saveIFC.py`, optimizer stages |
| Research hub + roadmap | `hub.html`, `research_roadmap.html` | static | — |
| 3D building explorer | `building_explorer.html` | static + `/outputs/*.glb` | `populate_building.py` (merged mode) |
| Synthetic towers | — | — | `make_tower_ifc.py` |
| Benchmark evidence | `/benchmark/*` | static mount | `benchmark/*.py` build scripts |

**Data locations:** `data/generated_assets/` (catalog items + `manifest.json` — the single
source of truth for codes/engines), `data/buildings/` (+ `manifest.json` registry,
`_cache/` per-building geometry cache — version `v6`, bump `CACHE_VERSION` when cached
shapes change), `data/mesh_library_abo/` (ABO retrieval library), `outputs/` (generated
GLBs incl. `*_populated.glb` explorer models), `demo/app_out/bldg_*/` (per-building movable
pieces).

---

## 3. How the pipeline works (the invariants)

1. **One gate:** nothing reaches a catalog or a room without repair → `saveIFC` → IFC4
   validation. Rejects are reported, never shipped.
2. **Honesty:** capacity refusals, dropped items, unreachable items are always surfaced
   with reasons — never silently fixed or hidden.
3. **Solve frame:** rooms, obstacles, zones and all 2D math live in the building's
   DE-ROTATED local frame (theta from dominant wall orientation); world positions are
   produced only at export. Never mix frames.
4. **Obstacles carry z-ranges** — a room only sees its own storey's walls/stairs.
5. **All floors with rooms are included** — never filter storeys by furnishability.
6. **Walking paths are sacred:** doors, doorless openings and wall gaps get keep-clears;
   pass-through rooms refuse furniture in the corridor.
7. **ASR is the default for workplace rooms** (`SCS_ASR=0` reverts): legal 8 m² + 6 m²
   staffing caps, 1.5 m²/1.0 m movement areas at desks, A1.8 route widths.
8. **Everything additive:** new room types/categories append after existing entries so
   current behavior never changes (user directive).
9. **Bug test after every change** (user directive): the two suites above + a regression
   probe of an unaffected building.

---

## 4. How to extend (recipes)

**Add a furniture category:** (1) `populate_building.py`: `TARGET_DIMS` +
`_FURN_FALLBACK` color + a procedural mesh (or rely on uploads) + `load_assets()`
setdefault; (2) `catalog.py`: `CATALOG_META` row (IFC class, dims, color);
(3) `rule_packs.py`: `_CATEGORY_ARCHETYPE` mapping (or let geometry inference handle it);
(4) `frontend/js/buildingMode.js` + `roomBuilder.js`: `FOOT` footprint for the capacity
guard. Follow the "tier-2" commit as the template.

**Add a room type:** `TYPE_KEYWORDS` (append AFTER existing keys, multi-language),
a `smart_furnish` branch, a `ROOM_TYPES` pack in `rule_packs.py`. If it needs special
placement (like lecture rows), add a pre-pass before the solver like the presentation
branch and feed leftovers to the solver.

**Add a building:** drop the .ifc in the app (or `POST /api/buildings/upload`). Check its
license first and record it in `docs/BUILDINGS_PROVENANCE.md`. For tall variants:
`python backend/python-scripts/make_tower_ifc.py <src> <out> --copies N` (derivative-
permitting sources only).

**Add an engine:** follow `deliverable/manuals/README.md` ops playbook; meshes enter via
`benchmark/ingest_pod_results.py` (IFC4 gate, engine badge, numbering).

**Change ergonomic numbers:** `rule_packs.py` only — `ANTHRO`, `ASR`, per-type packs.
Cite the standard in a comment; `docs/ASR_COMPLIANCE.md` documents the legal basis.

---

## 5. Code commenting convention

Every Python module carries a header docstring stating its role and contracts; dense
inline comments explain WHY (standards citations, exporter quirks, historical bugs like
the sideways-flip or the fat-AABB traps). Frontend modules open with a purpose block and
the endpoints they touch. When you change behavior, update the comment that justified the
old behavior — stale WHY-comments are worse than none.

---

## 6. Troubleshooting quick table

| Symptom | Likely cause | Fix |
|---|---|---|
| White furniture in viewers | vertex-color-only GLB (xeokit ignores COLOR_0) | bake PBR `baseColorFactor` (see `_load_colored_furniture`) |
| Furniture inside walls | frame mismatch or missing keep-outs | check `theta`, cache version, storey z-filter |
| Phantom clashes / camera to nowhere | world-vs-local frame mixing in JS | use `window.bFrame.toLocal/toWorld` everywhere |
| Rooms missing from cards | storey filter or space geometry failure | run `test_floor_dissection.py`; check `space_extent` |
| Generate returns a melted blob | bad segmentation mask or mislabel | rembg default; pick an explicit chair-base style |
| Upload probe times out | server busy with a big populate | retry when idle; probes queue behind the building queue |
| 504 on huge populate | route timeout on first geometry scan | rerun after the cache is built — repeats are solver-only |
