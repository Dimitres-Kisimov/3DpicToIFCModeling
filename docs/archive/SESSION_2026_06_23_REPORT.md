# Session Report — 2026-06-23

**Branch:** `app-development`
**Focus:** Master the human room-layout engine; make the web app usable for interactive
room-building (pick → generate → preview → export); harden it.

---

## 1. Goal of the session
- Understand & **master** the "human/functional" layout part of the project.
- Be able to **visualize** a room and **select items interactively**, then see the result.
- End state wanted: user can build a room, restart freely, and **nothing is saved until Export**.

## 2. What we reviewed
- Walked the repo branches. The two newest (2026-06-21) are `app-development` (web app shell:
  catalog picker, room editor, constrained generate) and `demo/room-population` (sim v1).
  `app-development` is the superset — used throughout.
- Authoritative status doc: `docs/FINDINGS.md` (photo → object table → AI room layout → IFC/viewer).

## 3. Mastery: the 3-layer layout engine (verified, not just read)
Layers, bottom-up:
1. **Rule packs** (`rule_packs.py`) — ergonomic numbers from standards (Neufert area/person,
   ADA clearances, IBC door keep-clear, clearance presets, per-room-type `groups`).
2. **CP-SAT packing** (`spatial_layout.py`) — 10 cm grid, 0°/90° rotation, `AddNoOverlap2D`
   (furniture + obstacle keep-outs), **wall-affinity objective** (perimeter items minimise
   distance-to-nearest-wall → centre stays open).
3. **Functional anchoring + facing** (`build_room_scene.py`) — children (chair/monitor/lamp)
   are folded into a desk's **reserved solver box** (group can't collide), then split out:
   desk shifted to the wall end, chair placed in front, **seat-facing inferred from mesh
   geometry** via `_chair_forward_xz()` so the chair turns to face the desk regardless of the
   source mesh's authored orientation.

**Verification:** hand-traced Workstation A through all three layers, then ran
`build_room_scene.py` on `demo/office15_obstacles_spec.json`. Real solver output matched the
hand-trace **to the centimetre** (desk/chair/monitor/lamp x,z). The chair-facing came out
≈ −0.5° (geometry-corrected) vs the representative 180° — both correctly face the desk; this
proved why geometry-based facing beats a hard-coded angle.

## 4. The web app — brought up and hardened
Ran the Flask app: `python backend/app_server.py` → http://localhost:8000/
(pick categories + counts, room size/type, Generate → 3D + object table + Export CSV/IFC).

Bugs found & fixed this session (all in `demo/app.js`, `demo/app.html`, `backend/app_server.py`):

1. **Camera drift** → added a **Lock toggle** (🔒/🔓) in the viewer toolbar.
2. **Empty catalog / dead UI** — root cause: an init-time `cc.active = false` threw in this
   xeokit build, and a thrown error in an ES module aborts the whole script, so `loadCatalog()`
   never ran. Fixed: removed the unsafe init line, guarded the lock (try/catch + null checks),
   moved `loadCatalog()` to run first.
3. **Browser served stale `app.js`** (Arc ignored no-cache) → added **cache-bust** `app.js?v=N`
   and an on-screen **error surface** (`window.onerror` → top message bar) to stop guessing.
4. **Real blocker surfaced: WebGL fails** — `_initWebGL` can't get a context (browser WebGL
   **context limit** from ~20 open tabs, and/or hardware acceleration off). Made the viewer
   **degrade gracefully**: `new Viewer()` wrapped in try/catch; if WebGL is unavailable the app
   still lets you pick items, Generate, and Export — just no live 3D. `loadScene`/`walls`/lock
   all null-guarded.
5. **Visualized without browser WebGL** — server-side `render_scene.py` floor-plan/angle PNGs,
   and opened `scene.glb` in **native Windows 3D Viewer**.
6. **"Not quite right" layout** — diagnosed: (a) the viewed `scene.glb` was a **stale** earlier
   Generate (file desync from rapid regenerates); (b) `abo=False` categories (side_table,
   filing_cabinet, monitor, coffee_table) render as **ugly placeholder shapes** (the "wireframe
   cage"); (c) chairs are bulky **armchair** meshes placed loosely. The layout **logic is sound**
   — overlap check found **no real collisions** (only monitors/lamps correctly sitting on desks).
7. **Reset + ephemeral preview** (the user's requirement: *nothing saved until Export*):
   - Added **"Reset everything"** button + `reset()` — clears counts, obstacles/doors, 3D scene,
     object table, and room inputs back to 8×6 / Office / ADA-off.
   - `app_out` is now an explicit **scratch preview** dir. Added `_clear_scratch()` +
     `POST /api/reset`; scratch is wiped on **reset** and on **server startup**. `reset()` calls
     the endpoint. Generate writes only transient preview files; **Export (CSV/IFC) is the only
     save** (downloads to the user's machine).

## 5. Current state
- Server running (restarted with new code) on http://localhost:8000/. Client at `app.js?v=7`.
- Verified: `/`, `/api/catalog`, `POST /api/reset` all 200; scratch dir empties on reset/startup.
- **Modified, uncommitted:** `demo/app.html`, `demo/app.js`, `backend/app_server.py`.

## 6. Open items / TODO
- [ ] **3D preview** still depends on the user's browser WebGL — close tabs / enable hardware
      acceleration / try Chrome or Edge; or rely on native 3D Viewer + server-side renders.
- [ ] **Fix `abo=False` placeholder meshes** (side_table, filing_cabinet, monitor, coffee_table)
      → clean box meshes so nothing renders as a wireframe cage.
- [ ] **Chair refinement** — tuck chairs closer / use proper task-chair meshes instead of armchairs.
- [ ] **Desktop (PySide `.exe`)** — Export should use a native "Save As…" dialog (web version
      can only download to the browser's Downloads folder).
- [ ] **Capacity finder** (pending "B") — turn CP-SAT into a "max items that fit" tool to answer
      the real space-limit question (add items until INFEASIBLE, or `Maximize(placed)`).

## 7. How to run
```
python backend/app_server.py          # serves http://localhost:8000/
# pick items -> Generate (preview) -> happy? Export. Not happy? Reset -> repeat.
```
