# Handoff → Fable 5 (SCS Photo-to-BIM, Part 2)

You are continuing an in-progress project. Work on branch **`part2-ergonomics-one-app`** (not `main`).
Do not touch Part 1 unless asked.

## READ THESE FIRST, IN THIS ORDER (full picture)
1. **This file** — state, environment, next steps, gotchas.
2. **`docs/CODEBASE_MAP.md`** — the whole system: two-app topology, every subsystem→file, the object
   universe, the engine gaps, project facts. Start here to understand the code without re-exploring.
3. **`docs/PART2_ERGONOMICS_AND_ONE_APP_PLAN.md`** — the Part-2 design (workstreams A–E, verification).
4. **`docs/WORK_LOG_2026-07-06.md`** — everything done this session + comparison artifacts.
5. Part 1 reference: **`docs/office_chair_base_graft/README.md`**, **`docs/IFC_OPTIMIZER.md`**.
6. Older context (as needed): `docs/OPTIMIZATION_GUIDE.md`, `OPTIMIZATION_WORK_AND_VISUALS.md`,
   `SCS_MONOGRAPH_Photo_to_IFC.md`, `REPORT_IFC_to_3D_and_Progress_2026-07-01.md`.

The plan (#3) and codebase map (#2) contain exact `file:line` references for every subsystem you'll
touch — use them so you don't have to re-derive the architecture.

## What this project is
Photo → 3D → IFC pipeline for SCS (Bildungscampus). Two apps today that MUST become one:
- **Node :3000** (`backend/server.js`, `frontend/`) — photo→3D object generator (TripoSR) + IFC export.
- **Flask :8000** (`backend/app_server.py`, `demo/app.html`) — room builder: catalog selection,
  space/"not enough space" check, both room sources (user-defined + loaded Duplex IFC), drag-reposition.

## Environment (hard facts — verify before relying)
- OS Windows; **GPU = RTX 4050 Laptop, 6 GB** (~3.8 GB free at rest). Generation barely fits ONE job.
- Heavy/pinned Python (trimesh/ifcopenshell/pymeshfix/ortools):
  `C:\Users\dimik\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
- Start servers **detached** so they survive: PowerShell `Start-Process node -ArgumentList "backend/server.js" ...`.
- Node generation path spawns Python subprocesses (fresh process per job → VRAM released on exit).

## Done this session (committed)
- **Part 1 (branch `redesign-generator-ui`):** office-chair base graft + IFC optimizer — see
  `docs/office_chair_base_graft/README.md`, `docs/IFC_OPTIMIZER.md`.
- **A1** — object-agnostic archetypes + `ANTHRO` constants in `backend/python-scripts/rule_packs.py`
  (`archetype_of`, `placement_profile`). This is the foundation the solver work builds on.
- **D (GPU safety)** — `backend/services/gpuQueue.js`, wired in `backend/routes/apiRoutes.js`.
  Serializes GPU jobs to 1 (verified: 2 concurrent generations → peak 5.47/6.14 GB, no OOM). KEEP THIS.
- **D (catalog speed)** — forced `SCS_RETRIEVAL_THRESHOLD=0` for the catalog engine in `apiRoutes.js`
  so "Fast — from catalog" uses the catalog instead of secretly generating (53 s → 22 s).

## Next steps (in order — see the plan for detail)
1. **D warm-model worker:** a persistent Python process holding DETR/Depth/DINOv2 (on CPU, to avoid
   VRAM contention with TripoSR) so catalog recall drops ~22 s → ~3–5 s. Add a result cache by image hash.
2. **A2** — feed `placement_profile()` interaction zones into the CP-SAT solver
   (`backend/python-scripts/spatial_layout.py`, `_solve_layout_ortools`) as extra reserved rectangles;
   extend rotation from 0/90° to 0/90/180/270°.
3. **A3 + A3b** — circulation flood-fill (door → every access zone at ≥ `min_aisle`) and a generalized
   `extract_room_obstacles(ifc, space)` (columns/walls/beams) reusing `populate_building.py`.
4. **A4** — turn the current all-or-nothing solve into a space-gated result with per-item "not enough
   space" diagnostics (`build_room_scene.py` feasibility at ~line 243).
5. **A6** — generalize `_chair_forward_xz` facing to all archetypes; persist relationships into IFC.
6. **B+E** — reimplement the ~12 Flask endpoints (`app_server.py`) as Node routes spawning the SAME
   Python; one unified UI; retire Flask. Deployment-ready single app.
7. **C+C2** — 2D floor-plan editor (manual exact placement, live 3D sync, collision incl. building
   pillars/walls) + catalog 3D previews for manually-added items.

## Gotchas (do not regress)
- Never run two GPU generations at once (OOM). The `gpuQueue` enforces it.
- Do NOT re-add seat-leveling or X-up canonicalize to `graft_chair_base.py` (broke orientation).
- Verify orientation changes in the ACTUAL app viewer (`[180,0,90]`), not offline renders.
- The CP-SAT solver already consumes `obstacles` — A3b just needs to feed building elements in.

## How to run / verify
- `node backend/server.js` (→ :3000) and `python backend/app_server.py` (→ :8000).
- Generate: `POST /api/generate` (multipart: `model=triposr|detect`, `image`, `graftBase=1` for chairs).
- Room layout (Flask): `POST /api/generate` with room + item picks (see `demo/app.js`).
- Solver unit test target: `python backend/python-scripts/spatial_layout.py '<room_json>' '<objects_json>'`.
