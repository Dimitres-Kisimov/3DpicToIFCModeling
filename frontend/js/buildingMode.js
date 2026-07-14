/**
 * buildingMode — the "Building" workspace: load a REAL architectural IFC, review
 * every furnishable room (grouped by FLOOR), edit the picks, populate — the
 * ergonomic solver routes around the building's own walls/beams/columns — then
 * navigate floor by floor: pick a storey to isolate it in 3D (section-plane cut)
 * and open its 2D floor plan (buildingPlan.js) to drag furniture precisely.
 *
 * Endpoints: /api/buildings, /api/building/:bid/rooms (now returns storeys +
 * per-room floor data), /populate, /save.
 * Shared viewer models: shell = "b-shell", each movable piece = "bp-<id>".
 */
(function () {
  const $ = (id) => document.getElementById(id);

  let initialized = false;
  let currentBuilding = '';
  let roomPicks = {};               // room name -> [categories]
  let allCategories = [];
  let storeys = [];                 // [{name, elevation, top}]
  let roomsData = [];               // rooms incl. storey/rect/obstacles
  let bTheta = 0;
  let density = 'medium';          // light | medium | dense — drives the suggested sets                   // building world-rotation (deg) — rooms/obstacles/zones
                                    // live in the solver's DE-ROTATED frame; pieces carry
                                    // world positions. All plan math runs in the local frame.
  function toLocal(px, py) {
    if (!bTheta) return [px, py];
    const r = -bTheta * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
    return [px * c - py * s, px * s + py * c];
  }
  function toWorld(lx, ly) {
    if (!bTheta) return [lx, ly];
    const r = bTheta * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
    return [lx * c - ly * s, lx * s + ly * c];
  }
  window.bFrame = { toLocal, toWorld };
  let currentFloor = null;          // storey name, or null = whole building
  const bPieces = {};               // piece id -> {model, pos, category, glb, dims, room}
  let bShell = null;
  let bSelected = null, bDragging = false;
  let camLocked = true;             // locked = pieces draggable without orbiting
  let sectionPlugin = null;
  const sectionPlanes = [];

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);
  const toast = (t, kind) => window.appShell && window.appShell.toast(t, kind);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();
  const loader = () => window.xeokitModule && window.xeokitModule.getLoader && window.xeokitModule.getLoader();

  // ------------------------------------------------------------------ rooms UI
  let registryMap = {};                 // id -> {name, status, profile}
  let genItems = [];                    // the user's OWN generated meshes [{id, category}]

  async function loadGenItems() {
    try {
      const cats = await (await fetch('/api/room/catalog')).json();
      const withGen = cats.filter((c) => c.generated_count > 0).map((c) => c.category);
      const lists = await Promise.all(withGen.map((c) =>
        fetch('/api/room/items/' + c).then((r) => r.json()).then((items) =>
          items.filter((it) => it.generated).map((it) => ({ id: it.id, category: c, code: it.code })))));
      genItems = lists.flat();
    } catch (e) { genItems = []; }
  }
  const genCat = (gid) => (genItems.find((g) => g.id === gid) || {}).category || 'item';
  const pickLabel = (c) => c.startsWith('gen:')
    ? '◆ ' + genCat(c.slice(4)).replace(/_/g, ' ') + ' (ours)'
    : c.replace(/_/g, ' ');

  async function loadBuildings(selectId) {
    try {
      const bs = await (await fetch('/api/buildings')).json();
      const sel = $('bSelect');
      const keep = selectId || sel.value;
      while (sel.options.length > 1) sel.remove(1);
      registryMap = {};
      bs.forEach((b) => {
        registryMap[b.id] = b;
        const o = document.createElement('option');
        o.value = b.id;
        o.textContent = b.name + (b.status === 'preparing' ? ' · preparing…' : '');
        sel.appendChild(o);
      });
      if (keep && registryMap[keep]) { sel.value = keep; }
    } catch (e) { banner('Buildings list failed to load.', true); }
  }

  function showProfile(bid) {
    const el = $('bProfile');
    const b = registryMap[bid];
    if (!b || !b.profile) { el.hidden = true; return; }
    const p = b.profile;
    el.textContent = `▤ ${p.storeys} floors · ${p.spaces} rooms · ${p.size_mb} MB` +
      (p.est_populate_min ? ` · ~${p.est_populate_min} min to populate` : '');
    if (p.warnings && p.warnings.length) el.textContent += ` · ⚠ ${p.warnings[0]}`;
    el.hidden = false;
  }

  // ---- add a building (.ifc upload -> probe -> registry -> background prepare)
  async function uploadBuilding(file) {
    if (!file) return;
    if (!/\.ifc$/i.test(file.name || '')) {
      banner('Only plain .ifc building files can be added.', true); return;
    }
    banner(`Checking ${file.name} — probing rooms, floors and size…`);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/buildings/upload', { method: 'POST', body: fd });
      const d = await r.json();
      if (!d.ok) { banner('Upload rejected: ' + (d.error || 'unknown'), true); return; }
      toast(`🏢 ${d.building.name} added — preparing its geometry in the background`, 'ok');
      await loadBuildings(d.building.id);
      onBuildingChange();
    } catch (e) { banner('Upload error: ' + e, true); }
  }

  // wipe the populated state (3D pieces + shell, floor cuts, table, picks) so
  // the user can re-configure and populate again from a clean slate. Also runs
  // on building switch — old pieces must never haunt the next building.
  function clearAll(resetPicks) {
    clearBuilding();
    currentFloor = null;
    ['bSave', 'bIfc', 'bDragHint', 'bFloors', 'bFixClashes', 'lockBtn', 'xrayBtn',
     'bPlanBtn', 'bClear'].forEach((id) => { const el = $(id); if (el) el.hidden = true; });
    if (window.buildingPlan && window.buildingPlan.isOpen()) window.buildingPlan.toggle(false);
    const tb = $('tableRows');
    if (tb) tb.innerHTML = '';
    $('tableMeta').textContent = '';
    if (resetPicks) {
      roomPicks = {};
      renderRoomCards();
    }
    if (currentBuilding) {
      fetch(`/api/building/${currentBuilding}/clear`, { method: 'POST' }).catch(() => {});
    }
  }

  async function onBuildingChange() {
    clearAll(false);                       // never carry the previous building's pieces
    currentBuilding = $('bSelect').value;
    const wrap = $('bRooms');
    wrap.innerHTML = '';
    roomPicks = {};
    storeys = []; roomsData = [];
    $('bPopulate').hidden = !currentBuilding;
    showProfile(currentBuilding);
    if (!currentBuilding) return;
    const prof = (registryMap[currentBuilding] || {}).profile;
    if (prof && prof.est_populate_min > 1) {
      $('bPopulate').textContent = `🏢 Populate building (~${prof.est_populate_min} min)`;
    } else {
      $('bPopulate').textContent = '🏢 Populate building';
    }
    wrap.innerHTML = '<p class="empty-state">Measuring every room in the IFC…</p>';
    try {
      const data = await (await fetch(`/api/building/${currentBuilding}/rooms`)).json();
      allCategories = data.categories || [];
      storeys = data.storeys || [];
      roomsData = data.rooms || [];
      bTheta = data.theta || 0;
      await loadGenItems();              // your generated meshes join the picker
      renderRoomCards();
      const dr = document.getElementById('bDensityRow');
      if (dr) dr.hidden = false;
      banner(`${roomsData.length} rooms across ${storeys.length} floors — pick a population level, edit the furniture, then Populate.`);
    } catch (e) {
      wrap.innerHTML = '';
      banner('Rooms load failed: ' + e, true);
    }
  }

  // group room cards under floor headers; mirrored same-name rooms on one
  // floor share picks — shown once with a ×N marker
  function suggestedFor(r) {
    if (density === 'light') return r.suggested_light || r.suggested || [];
    if (density === 'dense') return r.suggested_dense || r.suggested || [];
    return r.suggested || [];
  }
  function setDensity(d) {
    density = d;
    document.querySelectorAll('#bDensityRow [data-density]').forEach((b) =>
      b.classList.toggle('active', b.dataset.density === d));
    // reset every card to the tier's suggestion — edits after picking a tier stick
    roomsData.forEach((r) => { if (r.furnishable !== false) roomPicks[r.name] = [...suggestedFor(r)]; });
    renderRoomCards();
    toast(`Population set to ${d} — room suggestions updated (your edits after this stick).`, 'info');
  }
  document.querySelectorAll('#bDensityRow [data-density]').forEach((b) => {
    b.onclick = () => setDensity(b.dataset.density);
  });

  function renderRoomCards() {
    const wrap = $('bRooms');
    wrap.innerHTML = '';
    const order = storeys.length ? storeys.map((s) => s.name) : [null];
    order.forEach((sName) => {
      // sidebar cards: only rooms you can furnish (context spaces live on the 2D plan)
      const floorRooms = roomsData.filter((r) => (r.storey || null) === sName && r.furnishable !== false);
      if (!floorRooms.length) return;
      if (sName) {
        const h = document.createElement('div');
        h.className = 'storey-head';
        h.textContent = `▤ ${sName}`;
        wrap.appendChild(h);
      }
      const seenNames = new Set();
      floorRooms.forEach((r) => {
        if (seenNames.has(r.name)) return;
        seenNames.add(r.name);
        const copies = floorRooms.filter((x) => x.name === r.name).length;
        if (!(r.name in roomPicks)) roomPicks[r.name] = [...suggestedFor(r)];
        wrap.appendChild(roomCard(r, copies));
      });
    });
  }

  // ------------------------------------------------------- capacity guard
  // real footprints (mirrors populate_building.TARGET_DIMS) × a people-space
  // factor — the legroom / pull-out / approach zone the solver will reserve
  // anyway. Monitors/laptops ride on desks: zero floor cost.
  const FOOT = {
    bed: [3.28, 1.9], sofa: [1.80, 2.0], desk: [0.98, 2.0], table: [0.88, 2.2],
    office_chair: [0.36, 2.0], chair: [0.23, 2.0], stool: [0.18, 1.5],
    cabinet: [0.72, 1.8], bookshelf: [0.32, 1.8], filing_cabinet: [0.27, 1.8],
    coffee_table: [0.66, 1.5], side_table: [0.30, 1.3], lamp: [0.16, 1.2],
    planter: [0.16, 1.2], mirror: [0.09, 1.5], monitor: [0, 0], laptop: [0, 0],
    lectern: [0.30, 2.0], presentation_screen: [0.29, 1.2], whiteboard: [0.18, 1.2],
    projector: [0, 0], armchair: [0.64, 1.8], water_dispenser: [0.12, 1.5],
    coffee_machine: [0, 0], locker: [0.20, 1.8],
    printer: [0.36, 1.8], partition: [0.09, 1.3], phone_booth: [1.10, 1.6],
    fridge: [0.39, 1.8], microwave: [0, 0], coat_rack: [0.25, 1.4],
    flipchart: [0.46, 1.5], waste_bin: [0.12, 1.3],
    fire_extinguisher: [0.03, 1.0], first_aid_cabinet: [0.05, 1.0],
    server_rack: [0.48, 1.8],
  };
  const catOf = (pick) => pick.startsWith('gen:') ? genCat(pick.slice(4)) : pick;
  const spaceNeed = (picksArr) => picksArr.reduce((sum, p) => {
    const f = FOOT[catOf(p)] || [0.35, 1.5];
    return sum + f[0] * f[1];
  }, 0);
  // walls, door swings and the circulation aisle eat ~45% of any real room
  const usableArea = (r) => r.area * 0.55;

  function roomCard(r, copies) {
    const card = document.createElement('div');
    card.className = 'roomcard';
    const times = copies > 1 ? ` ×${copies}` : '';
    card.innerHTML =
      `<div class="roomhdr"><b>${r.name}${times}</b> <small>${r.type} · ${r.area} m²</small></div>` +
      `<div class="roomchips"></div>` +
      `<select class="roomadd"><option value="">+ add item…</option>` +
      allCategories.map((c) => `<option value="${c}">${c.replace(/_/g, ' ')}</option>`).join('') +
      (genItems.length
        ? `<optgroup label="◆ yours (generated)">` +
          genItems.map((g) => `<option value="gen:${g.id}">◆ ${g.code || (g.category.replace(/_/g, ' ') + ' · ' + g.id.slice(4, 10))}</option>`).join('') +
          `</optgroup>`
        : '') +
      `</select>`;
    const chips = card.querySelector('.roomchips');
    const render = () => {
      chips.innerHTML = '';
      roomPicks[r.name].forEach((c, i) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.textContent = pickLabel(c) + ' ✕';
        chip.title = 'click = remove · right-click = add copies';
        chip.onclick = () => { roomPicks[r.name].splice(i, 1); render(); };
        chip.oncontextmenu = (ev) => {            // fast duplicate: right-click -> N copies
          ev.preventDefault();
          const n = parseInt(prompt(`Add how many more "${pickLabel(c)}" to ${r.name}?`, '4'), 10);
          if (!n || n < 1) return;
          const usable = usableArea(r);
          let added = 0;
          for (let k = 0; k < n; k++) {
            if (spaceNeed([...roomPicks[r.name], c]) > usable) break;
            roomPicks[r.name].push(c);
            added++;
          }
          if (added < n) {
            toast(`🚫 Only ${added} of ${n} copies fit "${r.name}" — more would exceed its ` +
              `≈${usable.toFixed(1)} m² of usable space.`, 'bad');
          } else {
            toast(`＋${added} × ${pickLabel(c)} added to "${r.name}".`, 'info');
          }
          render();
        };
        chips.appendChild(chip);
      });
      if (!roomPicks[r.name].length) {
        const e = document.createElement('small');
        e.className = 'mut';
        e.textContent = '(empty)';
        chips.appendChild(e);
      }
    };
    render();
    card.querySelector('.roomadd').onchange = (e) => {
      const v = e.target.value;
      e.target.value = '';
      if (!v) return;
      const usable = usableArea(r);
      const need = spaceNeed([...roomPicks[r.name], v]);
      if (need > usable) {
        toast(`🚫 Not enough space in "${r.name}" — ${roomPicks[r.name].length + 1} items need ` +
          `≈${need.toFixed(1)} m² with people-space, but only ≈${usable.toFixed(1)} m² of its ` +
          `${r.area} m² is usable. Remove something first.`, 'bad');
        return;
      }
      roomPicks[r.name].push(v);
      if (need > usable * 0.8) {
        toast(`⚠ "${r.name}" is getting tight — ≈${need.toFixed(1)} of ${usable.toFixed(1)} m² usable ` +
          `is spoken for; the solver will drop whatever can't sit ergonomically.`, 'info');
      }
      render();
    };
    return card;
  }

  // ------------------------------------------------------------------ floors
  function renderFloorChips() {
    const wrap = $('bFloors');
    wrap.innerHTML = '';
    const mk = (label, floor) => {
      const b = document.createElement('button');
      b.className = 'floor-chip' + ((floor || '') === (currentFloor || '') ? ' active' : '');
      b.dataset.floor = floor || '';
      b.textContent = label;
      b.onclick = () => selectFloor(floor);
      wrap.appendChild(b);
    };
    mk('🏢 All floors', null);
    storeys.forEach((s) => mk(`▤ ${s.name}`, s.name));
    wrap.hidden = false;
  }

  function clearSections() {
    sectionPlanes.forEach((sp) => { try { sp.destroy(); } catch (e) {} });
    sectionPlanes.length = 0;
  }

  function selectFloor(name) {
    currentFloor = name;
    document.querySelectorAll('#bFloors .floor-chip').forEach((c) =>
      c.classList.toggle('active', c.dataset.floor === (name || '')));
    applyFloor();
    const st = storeys.find((s) => s.name === name);
    banner(st ? `▤ ${name} isolated — orbit it, or open the 🗺️ 2D floor plan.` : 'Showing the whole building.');
    if (window.buildingPlan) window.buildingPlan.floorChanged();
  }

  function applyFloor() {
    const v = viewer();
    if (!v) return;
    clearSections();
    const st = storeys.find((s) => s.name === currentFloor);
    if (st) {
      // dollhouse view: cut ~2.3 m above the floor (below the ceiling slab) so
      // you look INTO the storey; a second cut hides everything underneath it
      const cutTop = st.elevation + Math.min(2.3, (st.top - st.elevation) * 0.75);
      try {
        if (!sectionPlugin) sectionPlugin = new window.xeokit.SectionPlanesPlugin(v);
        sectionPlanes.push(sectionPlugin.createSectionPlane(
          { pos: [0, cutTop, 0], dir: [0, -1, 0] }));
        sectionPlanes.push(sectionPlugin.createSectionPlane(
          { pos: [0, st.elevation - 0.15, 0], dir: [0, 1, 0] }));
      } catch (e) { console.warn('section planes unavailable', e); }
    }
    Object.values(bPieces).forEach((p) => {
      const y = p.pos[1];
      const on = !st || (y >= st.elevation - 0.5 && y < st.top - 0.5);
      try { p.model.visible = on; } catch (e) {}
    });
  }

  // pieces/rooms of the CURRENT floor for the 2D plan (live references)
  function getFloorData() {
    const st = storeys.find((s) => s.name === currentFloor) || storeys[0] || null;
    const rooms = roomsData.filter((r) => !st || r.storey === st.name);
    const pieces = {};
    Object.entries(bPieces).forEach(([id, p]) => {
      const y = p.pos[1];
      if (!st || (y >= st.elevation - 0.5 && y < st.top - 0.5)) pieces[id] = p;
    });
    return { storey: st, rooms, pieces };
  }

  // ------------------------------------------------------------------ clash engine
  // One legality checker shared by the 2D plan AND the 3D drag: a piece must sit
  // fully inside a room, off the fixed elements, and clear of every other piece.
  function pieceRect(p) {
    const w = (p.dims && p.dims[0]) || 0.6;
    const d = (p.dims && p.dims[1]) || 0.6;
    const [cx, cy] = toLocal(p.pos[0], -p.pos[2]);
    return [cx - w / 2, cy - d / 2, w, d];
  }
  function rectsOverlap(a, b) {
    return Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]) > 0.02 &&
           Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]) > 0.02;
  }
  function floorBandOf(p) {
    return storeys.find((s) => p.pos[1] >= s.elevation - 0.5 && p.pos[1] < s.top - 0.5) || null;
  }
  // rooms of L-shaped plans overlap as bounding boxes — a piece is judged ONLY
  // against the room(s) that actually hold its centre (its named home room first),
  // never against a neighbour's walls bleeding into the overlap.
  function roomsOf(p, rooms) {
    const [cx, cz] = toLocal(p.pos[0], -p.pos[2]);
    const inside = rooms.filter((rm) =>
      cx >= rm.rect[0] - 0.01 && cx <= rm.rect[0] + rm.rect[2] + 0.01 &&
      cz >= rm.rect[1] - 0.01 && cz <= rm.rect[1] + rm.rect[3] + 0.01);
    const home = inside.filter((rm) => rm.name === p.room);
    return home.length ? home : inside;
  }
  function isLegalPiece(pid) {
    const p = bPieces[pid];
    if (!p) return true;
    if (p.elev > 0.01) return true;        // on-desk items live above the floor plane
    const st = floorBandOf(p);
    const rooms = roomsData.filter((r) => !st || r.storey === st.name);
    const r = pieceRect(p);
    const mine = roomsOf(p, rooms);
    const inRoom = mine.some((rm) =>
      r[0] >= rm.rect[0] - 0.01 && r[1] >= rm.rect[1] - 0.01 &&
      r[0] + r[2] <= rm.rect[0] + rm.rect[2] + 0.01 &&
      r[1] + r[3] <= rm.rect[1] + rm.rect[3] + 0.01);
    if (!inRoom) return false;
    for (const [oid, o] of Object.entries(bPieces)) {
      if (oid === pid || o.elev > 0.01) continue;
      if (st && !(o.pos[1] >= st.elevation - 0.5 && o.pos[1] < st.top - 0.5)) continue;
      // only neighbours sharing one of my rooms can truly collide
      if (!roomsOf(o, rooms).some((rm) => mine.includes(rm))) continue;
      if (rectsOverlap(r, pieceRect(o))) return false;
      // people-space is sacred: no footprint may invade another piece's zone
      for (const z of pieceZonesWorld(o)) {
        if (rectsOverlap(r, z)) return false;
      }
    }
    for (const rm of mine) {
      for (const ob of (rm.obstacles || [])) {
        if (rectsOverlap(r, [rm.rect[0] + ob.x, rm.rect[1] + ob.z, ob.width, ob.depth])) return false;
      }
    }
    return true;
  }
  function findClashes() {
    return new Set(Object.keys(bPieces).filter((pid) => !isLegalPiece(pid)));
  }
  // auto-fix: nudge each clashing piece outward in a spiral to its nearest legal spot
  function resolveClashes() {
    let fixed = 0;
    for (const pid of findClashes()) {
      if (isLegalPiece(pid)) continue;            // an earlier nudge may have freed it
      const p = bPieces[pid];
      const wx0 = p.pos[0], wz0 = p.pos[2];
      const [px, py] = toLocal(wx0, -wz0);        // spiral in the solver frame
      let done = false;
      for (let rad = 0.1; rad <= 2.4 && !done; rad += 0.1) {
        for (let a = 0; a < 16 && !done; a++) {
          const th = (Math.PI * 2 * a) / 16;
          const [wx, wy] = toWorld(px + rad * Math.cos(th), py + rad * Math.sin(th));
          p.pos[0] = Math.round(wx * 100) / 100;
          p.pos[2] = -Math.round(wy * 100) / 100;
          if (isLegalPiece(pid)) done = true;
        }
      }
      if (done) { fixed++; refreshPiece(pid); }
      else { p.pos[0] = wx0; p.pos[2] = wz0; }    // no free spot in reach — leave, stays marked
    }
    return { fixed, remaining: findClashes().size };
  }
  function updateClashUI() {
    const n = findClashes().size;
    const btn = $('bFixClashes');
    if (btn) {
      btn.hidden = n === 0;
      btn.textContent = `🧹 Resolve ${n} clash${n === 1 ? '' : 'es'}`;
    }
    return n;
  }

  // ------------------------------------------------------------------ room teleport
  function enterRoom(room) {
    const st = storeys.find((s) => s.name === room.storey);
    if (st && currentFloor !== st.name) selectFloor(st.name);
    if (window.buildingPlan && window.buildingPlan.isOpen()) window.buildingPlan.toggle(false);
    const v = viewer();
    if (!v) return;
    const [x0, y0, W, D] = room.rect;
    const e = st ? st.elevation : 0;
    const cs = [[x0, y0], [x0 + W, y0], [x0, y0 + D], [x0 + W, y0 + D]].map(([a, b]) => toWorld(a, b));
    const xs = cs.map((c) => c[0]), ys = cs.map((c) => c[1]);
    try {
      // fly INTO the room: its world box (viewer frame: z = -y_ifc), dollhouse cut open
      v.cameraFlight.flyTo({ aabb: [Math.min(...xs), e, -Math.max(...ys),
                                    Math.max(...xs), e + 2.2, -Math.min(...ys)], duration: 0.8 });
    } catch (err) {}
    banner(`🧊 ${room.name} · ${room.area} m² — drag pieces to rearrange; unlock the camera to orbit.`);
  }

  // ------------------------------------------------------------------ 3D pieces
  function clearBuilding() {
    if (bShell) { try { bShell.destroy(); } catch (e) {} bShell = null; }
    Object.values(bPieces).forEach((p) => { try { p.model.destroy(); } catch (e) {} });
    for (const k in bPieces) delete bPieces[k];
    bSelected = null;
    clearSections();
  }

  function loadBuilding(shellUrl, pieces, zones) {
    const g = loader();
    if (!g) { banner('3D viewer unavailable (no WebGL)', true); return; }
    clearBuilding();
    bShell = g.load({ id: 'b-shell', src: shellUrl + '?t=' + Date.now(), edges: true });
    if (bShell) bShell.on('loaded', () => {
      try { viewer().cameraFlight.jumpTo(bShell); } catch (e) {}
      if (window.appShell) window.appShell.applyVisibility();
      applyFloor();
    });
    pieces.forEach((pc) => {
      const model = g.load({ id: 'bp-' + pc.id, src: pc.glb + '?t=' + Date.now(), position: pc.pos.slice() });
      if (model) {
        model.on('error', (e) => console.warn('piece load error', pc.id, e));
        // zones stored RELATIVE to the piece's plan position — they ride along
        // when the user drags the piece (2D or 3D)
        const px = pc.pos[0], py = -pc.pos[2];
        const zonesRel = ((zones || {})[pc.id] || []).map(([zx, zy, zw, zd]) =>
          [zx - px, zy - py, zw, zd]);
        bPieces[pc.id] = { model, pos: pc.pos.slice(), category: pc.category,
                           glb: pc.glb, dims: pc.dims || null, room: pc.room || null,
                           elev: pc.elev || 0, zonesRel };
      }
    });
  }

  // world-XY people-space rects for a piece at its CURRENT position
  function pieceZonesWorld(p) {
    const px = p.pos[0], py = -p.pos[2];
    return (p.zonesRel || []).map(([dx, dy, w, d]) => {
      const [lcx, lcy] = toLocal(px + dx + w / 2, py + dy + d / 2);
      return [lcx - w / 2, lcy - d / 2, w, d];
    });
  }

  function pieceIdFromPick(pr) {
    if (!pr || !pr.entity) return null;
    const mid = (pr.entity.model && pr.entity.model.id) || pr.entity.id || '';
    return String(mid).startsWith('bp-') ? String(mid).slice(3) : null;
  }

  function setLock(locked) {
    camLocked = locked;
    const v = viewer();
    try { if (v) v.cameraControl.active = !locked; } catch (e) {}
    const b = $('lockBtn');
    if (b) b.textContent = locked ? '🔒 Locked' : '🔓 Free';
  }

  // ------------------------------------------------------------------ x-ray
  let xrayOn = false;
  function setXray(on) {
    const v = viewer();
    if (!v) return;
    xrayOn = on;
    try {
      const xm = v.scene.xrayMaterial;      // ghosted shell: furniture pops through
      xm.fillColor = [0.75, 0.81, 0.90];
      xm.fillAlpha = 0.12;
      xm.edgeColor = [0.35, 0.42, 0.55];
      xm.edgeAlpha = 0.35;
    } catch (e) {}
    Object.entries(viewer().scene.objects).forEach(([id, ent]) => {
      if (String(id).startsWith('shell-')) {
        try { ent.xrayed = on; } catch (e) {}
      }
    });
    const b = $('xrayBtn');
    if (b) b.textContent = on ? '🏢 Solid' : '👻 X-ray';
  }

  // reload a piece's GLB at its current position (guarantees the move shows)
  function refreshPiece(pid) {
    const p = bPieces[pid];
    if (!p) return;
    try { p.model.destroy(); } catch (_) {}
    p.model = loader().load({ id: 'bp-' + pid, src: p.glb + '?r=' + Date.now(), position: p.pos.slice() });
  }

  function wireDrag() {
    const v = viewer();
    if (!v) return;
    const cv = v.scene.canvas.canvas;      // the actual canvas element
    let dragStartPos = null;
    cv.addEventListener('pointerdown', (e) => {
      if (!Object.keys(bPieces).length) return;
      if (window.appShell && window.appShell.activeTab() !== 'building') return;
      const rect = cv.getBoundingClientRect();
      const pid = pieceIdFromPick(v.scene.pick({ canvasPos: [e.clientX - rect.left, e.clientY - rect.top] }));
      if (pid && bPieces[pid]) {
        bSelected = pid; bDragging = true;
        dragStartPos = bPieces[pid].pos.slice();
        try { v.cameraControl.active = false; } catch (_) {}
        banner('Dragging ' + bPieces[pid].category.replace(/_/g, ' ') + ' — release to drop it.');
      }
    });
    cv.addEventListener('pointermove', (e) => {
      if (!bDragging || !bSelected) return;
      const rect = cv.getBoundingClientRect();
      const pr = v.scene.pick({ canvasPos: [e.clientX - rect.left, e.clientY - rect.top], pickSurface: true });
      if (pr && pr.worldPos) {
        const p = bPieces[bSelected];
        p.pos = [pr.worldPos[0], p.pos[1], pr.worldPos[2]];
        try { p.model.position = p.pos; } catch (_) {}
      }
    });
    const endDrag = () => {
      if (bDragging && bSelected) {
        // 3D drops are validated too — clashes can't be created by dragging
        if (!isLegalPiece(bSelected) && dragStartPos) {
          bPieces[bSelected].pos = dragStartPos.slice();
          try { bPieces[bSelected].model.position = bPieces[bSelected].pos; } catch (_) {}
          banner('That spot clashes with a wall or another piece — put it somewhere clear.', true);
        } else {
          refreshPiece(bSelected);
          banner('Moved ' + bPieces[bSelected].category.replace(/_/g, ' ') + '. Drag more, or 💾 Save layout to keep it.');
        }
        updateClashUI();
        if (window.buildingPlan && window.buildingPlan.isOpen()) window.buildingPlan.floorChanged();
      }
      bDragging = false;
      try { v.cameraControl.active = !camLocked; } catch (_) {}
    };
    cv.addEventListener('pointerup', endDrag);
    cv.addEventListener('pointerleave', endDrag);
  }

  // ------------------------------------------------------------------ actions
  async function populate() {
    const btn = $('bPopulate');
    btn.disabled = true;
    btn.textContent = '⏳ Populating (~30–60 s)…';
    banner('Populating building — the solver is routing around walls, beams and columns…');
    try {
      const r = await fetch(`/api/building/${currentBuilding}/populate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ picks: roomPicks, density }),
      });
      const d = await r.json();
      if (!d.ok) { banner('Populate failed: ' + (d.error || 'unknown'), true); return; }
      banner(`✓ ${d.placed} pieces across ${d.rooms} rooms · ${d.clashes} clashes — pick a floor to explore.`, d.clashes > 0);
      toast(`🏢 Building populated: ${d.placed} pieces`, 'ok');
      // honest capacity verdict: whatever the solver could NOT fit is said out loud
      const droppedRooms = (d.schedule || []).filter((s) => (s.dropped || []).length);
      const nDropped = droppedRooms.reduce((n, s) => n + s.dropped.length, 0);
      if (nDropped > 0) {
        toast(`🚫 Not enough space for ${nDropped} item${nDropped === 1 ? '' : 's'} in ` +
          `${droppedRooms.length} room${droppedRooms.length === 1 ? '' : 's'} — the engine placed ` +
          `what fits ergonomically; the object table lists what didn't.`, 'bad');
      }
      currentFloor = null;
      loadBuilding(d.shell, d.pieces || [], d.zones || {});
      renderFloorChips();
      $('bSave').hidden = false;
      $('bIfc').hidden = false;
      $('bClear').hidden = false;
      $('bDragHint').hidden = false;
      $('lockBtn').hidden = false;
      $('bPlanBtn').hidden = false;
      $('xrayBtn').hidden = false;
      xrayOn = false;
      $('xrayBtn').textContent = '👻 X-ray';
      setLock(true);
      setTimeout(updateClashUI, 400);      // offer 🧹 if anything overlaps
      const tb = $('tableRows');
      tb.innerHTML = '';
      $('tableMeta').textContent = ` · ${d.rooms} rooms · ${d.placed} placed`;
      (d.schedule || []).forEach((s, i) => {
        const tr = document.createElement('tr');
        tr.style.setProperty('--i', i);
        const total = s.items.length + ((s.dropped || []).length);
        // honest per-room ergonomics report — same voice as the room builder
        let note = '';
        if ((s.dropped || []).length) {
          note += `<br><span style="color:#d64545">✗ no space: ${s.dropped.join(', ')}</span>`;
        }
        if ((s.unreachable || []).length) {
          note += `<br><span style="color:#e0812b">⚠ hard to reach: ${s.unreachable.join(', ')}</span>`;
        }
        tr.innerHTML = `<td>${s.room}</td><td class="ifc">${s.type}</td>` +
                       `<td>${s.placed}/${total} placed${note}</td>`;
        tb.appendChild(tr);
      });
      wireDrag();
    } catch (e) { banner('Populate error: ' + e, true); }
    finally { btn.disabled = false; btn.textContent = '🏢 Populate building'; }
  }

  async function saveBuilding() {
    const positions = {};
    Object.entries(bPieces).forEach(([id, p]) => { positions[id] = p.pos; });
    banner('Saving layout & building the export GLB…');
    try {
      const r = await fetch(`/api/building/${currentBuilding}/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      });
      const d = await r.json();
      if (!d.ok) { banner('Save failed: ' + d.error, true); return; }
      banner('✓ Saved. Downloading building GLB…');
      const blob = await (await fetch(d.glb + '?t=' + Date.now())).blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'building.glb';
      a.click();
      URL.revokeObjectURL(a.href);
      toast('💾 building.glb downloaded', 'ok');
    } catch (e) { banner('Save error: ' + e, true); }
  }

  async function exportIfc() {
    const positions = {};
    Object.entries(bPieces).forEach(([id, p]) => { positions[id] = p.pos; });
    const btn = $('bIfc');
    btn.disabled = true;
    btn.textContent = '⏳ Writing BIM file…';
    banner('Writing the IFC — architecture + every placed piece as IfcFurnishingElement…');
    try {
      const r = await fetch(`/api/building/${currentBuilding}/export-ifc`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      });
      const d = await r.json();
      if (!d.ok) { banner('IFC export failed: ' + (d.error || 'unknown'), true); return; }
      banner(`✓ IFC ready — ${d.furniture} furniture elements, ${d.mb} MB. Downloading…`);
      const blob = await (await fetch(d.ifc + '?t=' + Date.now())).blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${(registryMap[currentBuilding] || {}).name || 'building'} - populated.ifc`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast(`🏗️ populated IFC downloaded (${d.furniture} furnishings)`, 'ok');
    } catch (e) { banner('IFC export error: ' + e, true); }
    finally { btn.disabled = false; btn.textContent = '🏗️ Download IFC (BIM, incl. furniture)'; }
  }

  // ------------------------------------------------------------------ shell hooks
  function onTabLeave() {
    clearSections();                       // section planes cut EVERY model — never
    if (window.buildingPlan && window.buildingPlan.isOpen()) {   // leak into other tabs
      window.buildingPlan.toggle(false);
    }
  }
  function onTabEnter() { applyFloor(); }  // re-apply floor filter after shell visibility

  // ------------------------------------------------------------------ init
  function ensureInit() {
    if (initialized) return;
    initialized = true;
    loadBuildings();
    $('bSelect').onchange = onBuildingChange;
    $('bPopulate').onclick = populate;
    $('bSave').onclick = saveBuilding;
    $('bIfc').onclick = exportIfc;
    $('lockBtn').onclick = () => setLock(!camLocked);
    $('xrayBtn').onclick = () => setXray(!xrayOn);
    $('bClear').onclick = () => {
      clearAll(true);
      banner('🧼 Cleared. Fresh suggestions loaded — adjust the picks and Populate again.');
      toast('Building reset — nothing saved unless you had downloaded it', 'info');
    };
    $('bFixClashes').onclick = () => {
      const res = resolveClashes();
      updateClashUI();
      if (window.buildingPlan && window.buildingPlan.isOpen()) window.buildingPlan.floorChanged();
      banner(res.remaining === 0
        ? `🧹 ${res.fixed} clash${res.fixed === 1 ? '' : 'es'} resolved — everything sits clear now.`
        : `🧹 Fixed ${res.fixed}; ${res.remaining} piece(s) have no free spot nearby — drag them somewhere clear.`,
        res.remaining > 0);
    };

    // add-building dropzone
    const dz = $('bAddZone'), bf = $('bAddFile');
    if (dz && bf) {
      dz.addEventListener('click', () => bf.click());
      bf.addEventListener('change', () => { if (bf.files[0]) uploadBuilding(bf.files[0]); bf.value = ''; });
      ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
      ['dragleave', 'dragend'].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove('drag')));
      dz.addEventListener('drop', (e) => {
        e.preventDefault(); dz.classList.remove('drag');
        const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) uploadBuilding(f);
      });
    }
  }

  window.buildingMode = { ensureInit, hasContent: () => !!bShell, getFloorData,
                          selectFloor, currentFloor: () => currentFloor,
                          refreshPiece, onTabLeave, onTabEnter, pieceZonesWorld,
                          isLegalPiece, findClashes, resolveClashes, enterRoom };
})();
