/**
 * buildingMode — the "Building" workspace: load a REAL architectural IFC, review
 * every furnishable room with a smart suggestion, edit the picks, populate — the
 * ergonomic solver routes around the building's own walls/beams/columns — then
 * drag any piece in 3D and save the final layout as one GLB.
 *
 * Endpoints: /api/buildings, /api/building/:bid/rooms, /populate, /save.
 * Shared viewer models: shell = "b-shell", each movable piece = "bp-<id>".
 */
(function () {
  const $ = (id) => document.getElementById(id);

  let initialized = false;
  let currentBuilding = '';
  let roomPicks = {};               // room name -> [categories]
  let allCategories = [];
  const bPieces = {};               // piece id -> {model, pos, category, glb}
  let bShell = null;
  let bSelected = null, bDragging = false;
  let camLocked = true;             // locked = pieces draggable without orbiting

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);
  const toast = (t, kind) => window.appShell && window.appShell.toast(t, kind);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();
  const loader = () => window.xeokitModule && window.xeokitModule.getLoader && window.xeokitModule.getLoader();

  // ------------------------------------------------------------------ rooms UI
  async function loadBuildings() {
    try {
      const bs = await (await fetch('/api/buildings')).json();
      const sel = $('bSelect');
      bs.forEach((b) => {
        const o = document.createElement('option');
        o.value = b.id;
        o.textContent = b.name;
        sel.appendChild(o);
      });
    } catch (e) { banner('Buildings list failed to load.', true); }
  }

  async function onBuildingChange() {
    currentBuilding = $('bSelect').value;
    const wrap = $('bRooms');
    wrap.innerHTML = '';
    roomPicks = {};
    $('bPopulate').hidden = !currentBuilding;
    $('bSave').hidden = true;
    $('bDragHint').hidden = true;
    if (!currentBuilding) return;
    wrap.innerHTML = '<p class="empty-state">Measuring every room in the IFC…</p>';
    try {
      const data = await (await fetch(`/api/building/${currentBuilding}/rooms`)).json();
      allCategories = data.categories || [];
      wrap.innerHTML = '';
      data.rooms.forEach((r) => {
        roomPicks[r.name] = [...r.suggested];
        wrap.appendChild(roomCard(r));
      });
      banner(`${data.rooms.length} rooms found — edit each room's furniture, then Populate.`);
    } catch (e) {
      wrap.innerHTML = '';
      banner('Rooms load failed: ' + e, true);
    }
  }

  function roomCard(r) {
    const card = document.createElement('div');
    card.className = 'roomcard';
    card.innerHTML =
      `<div class="roomhdr"><b>${r.name}</b> <small>${r.type} · ${r.area} m²</small></div>` +
      `<div class="roomchips"></div>` +
      `<select class="roomadd"><option value="">+ add item…</option>` +
      allCategories.map((c) => `<option value="${c}">${c.replace(/_/g, ' ')}</option>`).join('') +
      `</select>`;
    const chips = card.querySelector('.roomchips');
    const render = () => {
      chips.innerHTML = '';
      roomPicks[r.name].forEach((c, i) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.textContent = c.replace(/_/g, ' ') + ' ✕';
        chip.onclick = () => { roomPicks[r.name].splice(i, 1); render(); };
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
      if (e.target.value) { roomPicks[r.name].push(e.target.value); e.target.value = ''; render(); }
    };
    return card;
  }

  // ------------------------------------------------------------------ 3D pieces
  function clearBuilding() {
    if (bShell) { try { bShell.destroy(); } catch (e) {} bShell = null; }
    Object.values(bPieces).forEach((p) => { try { p.model.destroy(); } catch (e) {} });
    for (const k in bPieces) delete bPieces[k];
    bSelected = null;
  }

  function loadBuilding(shellUrl, pieces) {
    const g = loader();
    if (!g) { banner('3D viewer unavailable (no WebGL)', true); return; }
    clearBuilding();
    bShell = g.load({ id: 'b-shell', src: shellUrl + '?t=' + Date.now(), edges: true });
    if (bShell) bShell.on('loaded', () => {
      try { viewer().cameraFlight.jumpTo(bShell); } catch (e) {}
      if (window.appShell) window.appShell.applyVisibility();
    });
    pieces.forEach((pc) => {
      const model = g.load({ id: 'bp-' + pc.id, src: pc.glb + '?t=' + Date.now(), position: pc.pos.slice() });
      if (model) {
        model.on('error', (e) => console.warn('piece load error', pc.id, e));
        bPieces[pc.id] = { model, pos: pc.pos.slice(), category: pc.category, glb: pc.glb };
      }
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

  function wireDrag() {
    const v = viewer();
    if (!v) return;
    const cv = v.scene.canvas.canvas;      // the actual canvas element
    cv.addEventListener('pointerdown', (e) => {
      if (!Object.keys(bPieces).length) return;
      if (window.appShell && window.appShell.activeTab() !== 'building') return;
      const rect = cv.getBoundingClientRect();
      const pid = pieceIdFromPick(v.scene.pick({ canvasPos: [e.clientX - rect.left, e.clientY - rect.top] }));
      if (pid && bPieces[pid]) {
        bSelected = pid; bDragging = true;
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
        const p = bPieces[bSelected];      // reload at final position so the move always shows
        try { p.model.destroy(); } catch (_) {}
        p.model = loader().load({ id: 'bp-' + bSelected, src: p.glb + '?r=' + Date.now(), position: p.pos.slice() });
        banner('Moved ' + p.category.replace(/_/g, ' ') + '. Drag more, or 💾 Save layout to keep it.');
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
        body: JSON.stringify({ picks: roomPicks }),
      });
      const d = await r.json();
      if (!d.ok) { banner('Populate failed: ' + (d.error || 'unknown'), true); return; }
      banner(`✓ ${d.placed} pieces across ${d.rooms} rooms · ${d.clashes} clashes — drag any piece to fine-tune.`, d.clashes > 0);
      toast(`🏢 Building populated: ${d.placed} pieces`, 'ok');
      loadBuilding(d.shell, d.pieces || []);
      $('bSave').hidden = false;
      $('bDragHint').hidden = false;
      $('lockBtn').hidden = false;
      setLock(true);
      const tb = $('tableRows');
      tb.innerHTML = '';
      $('tableMeta').textContent = ` · ${d.rooms} rooms · ${d.placed} placed`;
      (d.schedule || []).forEach((s, i) => {
        const tr = document.createElement('tr');
        tr.style.setProperty('--i', i);
        tr.innerHTML = `<td>${s.room}</td><td class="ifc">${s.type}</td><td>${s.placed}/${s.items.length} placed</td>`;
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

  // ------------------------------------------------------------------ init
  function ensureInit() {
    if (initialized) return;
    initialized = true;
    loadBuildings();
    $('bSelect').onchange = onBuildingChange;
    $('bPopulate').onclick = populate;
    $('bSave').onclick = saveBuilding;
    $('lockBtn').onclick = () => setLock(!camLocked);
  }

  window.buildingMode = { ensureInit, hasContent: () => !!bShell };
})();
