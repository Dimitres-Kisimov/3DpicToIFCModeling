/**
 * roomBuilder — the "Build a room" workspace (ported from the retired Flask demo UI).
 *
 * Flow: set room size/type → pick furniture (counts or specific meshes) → optional
 * obstacles/doors → Generate layout → the ergonomic solver places everything (or says
 * honestly that it doesn't fit) → 3D scene + object table + GLB/IFC/CSV export.
 *
 * Talks to the merged Node endpoints: /api/room/catalog, /api/room/items/:cat,
 * /api/room/layout, /api/room/upload, /api/room/reset. Uses the ONE shared xeokit
 * viewer (window.xeokitModule) — its room model always has id "room" so the shell
 * can show/hide it per tab.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  let initialized = false;
  let roomModel = null;           // the loaded xeokit scene model (id "room")
  let wallsVisible = true;
  let lastItems = [];             // last layout result rows (for CSV)
  const counts = {};              // category -> selected count
  const chosen = {};              // category -> [specific mesh ids]
  const obstacles = [], doors = [];
  let pickerCat = null;

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);
  const toast = (t, kind) => window.appShell && window.appShell.toast(t, kind);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();
  const loader = () => window.xeokitModule && window.xeokitModule.getLoader && window.xeokitModule.getLoader();

  // ------------------------------------------------------------------ catalog
  function browseBtnHTML(c) {
    // EVERY category gets the picker — procedural-only ones open with a hint on
    // how to add selectable variants (photo-generate with a declared type, or
    // upload IFCs into the category)
    const gen = c.generated_count || 0;
    const label = c.abo ? `⋯ pick (${c.abo_count})` : gen ? '⋯ pick' : '⋯ variants';
    const genTag = gen ? ` <span class="plus-ours">+${gen} ours</span>` : '';
    return `<button class="btn btn-tiny btn-browse" data-browse="${c.category}">${label}${genTag}</button>`;
  }

  async function loadCatalog() {
    const el = $('rbCatalog');
    try {
      const cats = await (await fetch('/api/room/catalog')).json();
      el.innerHTML = '';
      // "+ new category": declare a name, then upload one or many furniture
      // IFC files into it — they become numbered <name>-USER-NNN catalog items
      const addRow = document.createElement('div');
      addRow.className = 'catrow';
      addRow.innerHTML = `<span class="cat-name"><b>＋ New category…</b> <small>· upload your own furniture IFCs</small></span>` +
        `<span class="stepper"><button class="btn btn-tiny" id="rbNewCat">create</button></span>` +
        `<input type="file" id="rbNewCatFiles" accept=".ifc" multiple hidden>`;
      el.appendChild(addRow);
      const newBtn = addRow.querySelector('#rbNewCat');
      const fileIn = addRow.querySelector('#rbNewCatFiles');
      newBtn.onclick = () => {
        const name = prompt('Name of the new category (e.g. "ergo stool"):', '');
        if (!name || !name.trim()) return;
        fileIn.dataset.cat = name.trim();
        fileIn.click();
      };
      fileIn.onchange = async () => {
        if (!fileIn.files.length) return;
        const fd = new FormData();
        fd.append('category', fileIn.dataset.cat);
        [...fileIn.files].forEach((fl) => fd.append('files', fl));
        banner(`Uploading ${fileIn.files.length} IFC file(s) into "${fileIn.dataset.cat}"…`);
        try {
          const d = await (await fetch('/api/room/catalog/custom', { method: 'POST', body: fd })).json();
          const okN = (d.results || []).filter((r) => r.ok).length;
          const bad = (d.results || []).filter((r) => !r.ok);
          toast(`＋ ${okN} item(s) added to "${d.category || fileIn.dataset.cat}"` +
            (bad.length ? ` · ${bad.length} failed: ${bad.map((b) => b.error || b.file).join('; ')}` : ''),
            bad.length ? 'bad' : 'ok');
          await loadCatalog();
        } catch (e) { banner('Custom upload failed: ' + e, true); }
        fileIn.value = '';
      };
      cats.forEach((c) => {
        if (!(c.category in counts)) counts[c.category] = 0;
        const row = document.createElement('div');
        row.className = 'catrow';
        row.innerHTML =
          `<span class="cat-name">${c.label} <small>${c.custom ? '· yours' : (c.abo ? '· ABO' : '· prim')}</small></span>` +
          `<span class="stepper" id="rbStep-${c.category}">${browseBtnHTML(c)}` +
          `<button class="btn btn-tiny btn-step" data-c="${c.category}" data-d="-1">−</button>` +
          `<b id="rbN-${c.category}">${counts[c.category]}</b>` +
          `<button class="btn btn-tiny btn-step" data-c="${c.category}" data-d="1">+</button></span>`;
        el.appendChild(row);
      });
    } catch (e) {
      el.innerHTML = '<p class="empty-state">Catalog failed to load — is the server running?</p>';
    }
  }

  function total() { return Object.values(counts).reduce((a, b) => a + b, 0); }

  // No item-count limit — the budget is FLOOR AREA. Real footprint × people-
  // space factor per category (same model as the building path); screens ride
  // desks and wall decor costs no floor.
  const FOOT = {
    bed: [3.28, 1.9], sofa: [1.80, 2.0], desk: [0.98, 2.0], table: [0.88, 2.2],
    office_chair: [0.36, 2.0], chair: [0.23, 2.0], stool: [0.18, 1.5],
    cabinet: [0.72, 1.8], bookshelf: [0.32, 1.8], filing_cabinet: [0.27, 1.8],
    coffee_table: [0.66, 1.5], side_table: [0.30, 1.3], lamp: [0.16, 1.2],
    planter: [0.16, 1.2], mirror: [0, 0], monitor: [0, 0], laptop: [0, 0],
    clock: [0, 0], picture_frame: [0, 0],
  };
  const spaceNeed = () => Object.entries(counts).reduce((s, [c, n]) => {
    const f = FOOT[c] || [0.35, 1.5];
    return s + n * f[0] * f[1];
  }, 0);
  // walls, door swings and the circulation aisle eat ~45% of any room
  const usableArea = () => ((+$('rbWidth').value || 0) * (+$('rbDepth').value || 0)) * 0.55;

  function updateTotal() {
    const t = total();
    const need = spaceNeed(), usable = usableArea();
    const el = $('rbTotal');
    el.textContent = `${t} item${t === 1 ? '' : 's'} · ≈${need.toFixed(1)} / ${usable.toFixed(1)} m²`;
    el.style.color = need > usable ? 'var(--bad)' : '';
    el.title = 'furniture + people-space vs usable floor (~55% of the room)';
  }
  function itemsPayload() {
    return Object.entries(counts).filter(([, n]) => n > 0).map(([category, count]) => {
      const ids = chosen[category];
      return (ids && ids.length) ? { category, ids } : { category, count };
    });
  }

  // after an upload / auto-register, refresh one category's ⋯ button without
  // resetting any in-progress selection
  async function refreshCategoryBrowse(cat) {
    try {
      const cats = await (await fetch('/api/room/catalog')).json();
      const c = cats.find((x) => x.category === cat);
      const step = $('rbStep-' + cat);
      if (!c || !step) return;
      const existing = step.querySelector('button[data-browse]');
      const html = browseBtnHTML(c);
      if (existing) existing.outerHTML = html;
      else if (html) step.insertAdjacentHTML('afterbegin', html);
    } catch (e) { /* non-fatal */ }
  }

  // ------------------------------------------------------------------ picker
  async function openPicker(category) {
    pickerCat = category;
    $('pickerTitle').textContent = 'Choose ' + category.replace(/_/g, ' ') + ' — pick specific items';
    const grid = $('pickerGrid');
    grid.innerHTML = '<p class="empty-state">Loading…</p>';
    /* empty-state after load is handled below */
    $('picker').hidden = false;
    const items = await (await fetch('/api/room/items/' + category)).json();
    const sel = new Set(chosen[category] || []);
    grid.innerHTML = '';
    if (!items.length) {
      grid.innerHTML = '<p class="empty-state">No selectable variants yet — the clean ' +
        'parametric default is used when you add this item with +.<br><br>Add your own variants: ' +
        '<b>Generate object</b> → set “Object type” to this category and photograph one, or use ' +
        '<b>＋ New category…</b> with this category's exact name to upload furniture IFC files. ' +
        'Every variant gets a number (e.g. projector-TSR-001) and appears here.</p>';
    }
    items.forEach((it) => {
      const d = it.dims_m || [];
      const dim = (d[0] != null) ? `${d[0]}×${d[1]}×${d[2]} m` : '';
      const cell = document.createElement('div');
      cell.className = 'thumb' + (it.generated ? ' generated' : '') + (sel.has(it.id) ? ' sel' : '');
      const visual = it.generated
        ? (it.thumb_url
            ? `<img src="${it.thumb_url}" loading="lazy" title="made by you">`
            : `<div class="genph" title="made by you">◆</div>`)
        : `<img src="/thumb/${it.preview || it.thumb}" loading="lazy">`;
      const badge = it.generated
        ? `<span class="genbadge${it.engine ? ' eng' : ''}">${it.engine || 'OURS'}</span>` : '';
      const del = it.generated
        ? `<button class="gen-del" data-del="${it.id}" title="delete this generated item">✕</button>` : '';
      cell.innerHTML = badge + del + visual + `<div>${it.code || it.id}</div><div>${dim}</div>`;
      cell.onclick = (ev) => {
        if (ev.target && ev.target.dataset && ev.target.dataset.del) {
          ev.stopPropagation();
          deleteGenerated(it.id, category);
          return;
        }
        if (sel.has(it.id)) sel.delete(it.id); else sel.add(it.id);
        cell.classList.toggle('sel', sel.has(it.id));
        chosen[category] = [...sel];
        $('pickerCount').textContent = sel.size;
      };
      grid.appendChild(cell);
    });
    $('pickerCount').textContent = sel.size;
  }

  // delete one of the user's OWN generated items (files + manifest) — the ✕
  // on OURS cards. The generator's /outputs copy is untouched.
  async function deleteGenerated(gid, category) {
    try {
      const r = await fetch('/api/room/generated/' + gid, { method: 'DELETE' });
      const d = await r.json();
      if (!d.ok) { banner('Delete failed: ' + (d.error || '?'), true); return; }
      chosen[category] = (chosen[category] || []).filter((x) => x !== gid);
      toast(`✕ removed ${gid} from the catalog`, 'info');
      await refreshCategoryBrowse(category);
      openPicker(category);            // re-render without the deleted item
    } catch (e) { banner('Delete failed: ' + e, true); }
  }

  function closePicker() {
    if (pickerCat) {
      const n = (chosen[pickerCat] || []).length;
      if (n > 0) {                        // picking specific items sets the count
        counts[pickerCat] = n;
        const nb = $('rbN-' + pickerCat);
        if (nb) nb.textContent = n;
        updateTotal();
      }
    }
    $('picker').hidden = true;
    pickerCat = null;
  }

  // ------------------------------------------------------------------ upload
  async function uploadGenerated(file) {
    if (!file) return;
    const name = (file.name || '').toLowerCase();
    if (!name.endsWith('.glb') && !name.endsWith('.ifc')) {
      banner('Only .glb or .ifc files can be added.', true); return;
    }
    banner(`Uploading ${file.name}…`);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/room/upload', { method: 'POST', body: fd });
      const d = await r.json();
      if (!d.ok) { banner('Upload failed: ' + (d.error || 'unknown'), true); return; }
      const cat = d.item.category;
      await refreshCategoryBrowse(cat);
      if (pickerCat === cat) openPicker(cat);
      banner(`Added to “${cat.replace(/_/g, ' ')}” — open its ⋯ picker to select it.`);
      toast(`◆ ${file.name} → ${cat.replace(/_/g, ' ')}`, 'ok');
    } catch (e) { banner('Upload error: ' + e, true); }
  }

  // ------------------------------------------------------------------ chips
  function renderChips() {
    const el = $('rbChips');
    el.innerHTML = '';
    const addChip = (text, onClick) => {
      const c = document.createElement('span');
      c.className = 'chip';
      c.textContent = text + ' ✕';
      c.onclick = onClick;
      el.appendChild(c);
    };
    obstacles.forEach((o, i) => addChip(`column @${o.x},${o.z}`, () => { obstacles.splice(i, 1); renderChips(); }));
    doors.forEach((d, i) => addChip(`door @${d.x},${d.z}`, () => { doors.splice(i, 1); renderChips(); }));
  }

  // ------------------------------------------------------------------ 3D + results
  function loadScene(glb) {
    const g = loader();
    if (!g) return;                       // no WebGL — table/exports still work
    if (roomModel) { try { roomModel.destroy(); } catch (e) {} roomModel = null; }
    roomModel = g.load({ id: 'room', src: glb + '?t=' + Date.now(), edges: true });
    roomModel.on('loaded', () => {
      try { viewer().cameraFlight.jumpTo(roomModel); } catch (e) {}
      if (window.appShell) window.appShell.applyVisibility();
    });
    roomModel.on('error', (e) => banner('3D load error: ' + e, true));
  }

  function renderTable(its) {
    lastItems = its;
    const tb = $('tableRows');
    tb.innerHTML = '';
    its.forEach((it, i) => {
      const tr = document.createElement('tr');
      tr.style.setProperty('--i', i);
      tr.innerHTML =
        `<td><span class="swatch" style="background:${it.material_hex}"></span>${it.name}</td>` +
        `<td class="ifc">${it.ifc_class}</td><td>${it.width_m}×${it.depth_m}×${it.height_m}</td>`;
      tb.appendChild(tr);
    });
  }

  function setRenderFallback(render) {
    const img = $('vfallback'), btn = $('imgviewBtn');
    if (!render) return;
    img.src = render + '?t=' + Date.now();
    btn.hidden = false;
    if (!loader()) showImage(true);       // no WebGL → show the rendered image
  }
  function showImage(on) {
    const img = $('vfallback');
    img.hidden = !on;
    const btn = $('imgviewBtn');
    if (btn) btn.textContent = on ? '🧊 3D' : '🖼️ Image';
  }

  // Shared entry for both "Generate layout" and the top-bar Demo run —
  // takes a layout/demo API result and shows everything.
  function applyResult(d, opts = {}) {
    banner(d.message + (opts.demo ? ' (demo scene)' : ''), !d.feasible);
    $('tableMeta').textContent = ` · ${d.items.length} items · ${d.room.width}×${d.room.depth} m · ${d.solver}`;
    loadScene(d.glb);
    setRenderFallback(d.render);
    renderTable(d.items);
    // hand the layout to the 2D floor-plan editor (manual exact placement)
    if (window.planEditor) window.planEditor.setData({ room: d.room, items: d.items, zones: d.zones });
    if (!d.feasible) toast("Doesn't fit — the message above says exactly what to change.", 'bad');
    else if (opts.demo) toast('▶ Demo room ready — orbit it, open the 2D plan, export the IFC.', 'info');
  }

  // reload the room GLB after a server-side rebuild (2D-editor rotation edits)
  function reloadScene() { loadScene('/out/scene.glb'); }

  async function generate() {
    if (total() === 0) { banner('Pick at least one item first — the catalog is on the left.', true); return; }
    const need = spaceNeed(), usable = usableArea();
    if (need > usable) {
      banner(`🚫 Not enough space — ${total()} items need ≈${need.toFixed(1)} m² with people-space, ` +
        `but only ≈${usable.toFixed(1)} m² of the ${$('rbWidth').value}×${$('rbDepth').value} m room ` +
        `is usable. Remove items or enlarge the room.`, true);
      return;
    }
    const btn = $('rbGenerate');
    btn.disabled = true;
    btn.textContent = '⏳ Solving your room…';
    banner('Placing furniture ergonomically — solver at work…');
    const room = { width: +$('rbWidth').value, depth: +$('rbDepth').value, type: $('rbType').value, ada: $('rbAda').checked };
    try {
      const r = await fetch('/api/room/layout', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room, items: itemsPayload(), obstacles, doors }),
      });
      const d = await r.json();
      if (!d.ok) { banner('Error: ' + d.error, true); return; }
      applyResult(d);
    } catch (e) { banner('Request failed: ' + e, true); }
    finally { btn.disabled = false; btn.textContent = '✨ Generate layout'; }
  }

  function reset() {
    Object.keys(counts).forEach((c) => {
      counts[c] = 0;
      const n = $('rbN-' + c); if (n) n.textContent = '0';
    });
    Object.keys(chosen).forEach((c) => delete chosen[c]);
    updateTotal();
    obstacles.length = 0; doors.length = 0; renderChips();
    if (roomModel) { try { roomModel.destroy(); } catch (e) {} roomModel = null; }
    lastItems = [];
    $('tableRows').innerHTML = '';
    $('tableMeta').textContent = '';
    $('rbWidth').value = 8; $('rbDepth').value = 6;
    $('rbType').value = 'office'; $('rbAda').checked = false;
    showImage(false); $('imgviewBtn').hidden = true;
    if (window.planEditor && window.planEditor.isOpen()) window.planEditor.toggle(false);
    fetch('/api/room/reset', { method: 'POST' }).catch(() => {});
    banner('Fresh start. Nothing is saved until you Export. Pick items, then Generate.');
  }

  // ------------------------------------------------------------------ exports
  function downloadBlob(name, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function exportCsv() {
    if (!lastItems.length) { banner('Nothing to export — generate a layout first.', true); return; }
    const cols = ['id', 'name', 'ifc_class', 'category', 'width_m', 'depth_m', 'height_m', 'x', 'z', 'rotation_deg', 'source', 'license'];
    const lines = [cols.join(',')].concat(lastItems.map((it) => cols.map((c) => JSON.stringify(it[c] ?? '')).join(',')));
    downloadBlob('object_table.csv', new Blob([lines.join('\n')], { type: 'text/csv' }));
    toast('📄 Object table exported', 'ok');
  }
  async function exportGlb() {
    try {
      const r = await fetch('/out/scene.glb?t=' + Date.now());
      if (!r.ok) throw 0;
      downloadBlob('scene.glb', await r.blob());
      toast('🧊 scene.glb downloaded', 'ok');
    } catch (e) { banner('GLB not available — generate a layout first.', true); }
  }
  async function exportIfc() {
    try {
      const r = await fetch('/out/scene.ifc?t=' + Date.now());
      if (!r.ok) throw 0;
      downloadBlob('scene.ifc', await r.blob());
      toast('🏗️ scene.ifc downloaded — opens in Revit / ArchiCAD', 'ok');
    } catch (e) { banner('IFC not available — generate a layout first.', true); }
  }

  // ------------------------------------------------------------------ walls
  function toggleWalls() {
    const v = viewer();
    if (!v) return;
    wallsVisible = !wallsVisible;
    Object.keys(v.scene.objects).forEach((id) => {
      if (id.startsWith('room-wall')) {
        const o = v.scene.objects[id];
        if (o) o.visible = wallsVisible;
      }
    });
  }

  // ------------------------------------------------------------------ init
  function ensureInit() {
    if (initialized) return;
    initialized = true;
    loadCatalog();

    $('rbCatalog').addEventListener('click', (e) => {
      const br = e.target.closest('button[data-browse]');
      if (br) { openPicker(br.dataset.browse); return; }
      const b = e.target.closest('button[data-c]');
      if (!b) return;
      const c = b.dataset.c;
      const fitBefore = spaceNeed() <= usableArea();
      counts[c] = Math.max(0, counts[c] + (+b.dataset.d));
      chosen[c] = [];                     // manual count overrides specific picks
      $('rbN-' + c).textContent = counts[c];
      updateTotal();
      // say it the moment the order outgrows the floor (room can still be enlarged)
      if (fitBefore && +b.dataset.d > 0 && spaceNeed() > usableArea()) {
        toast(`🚫 Not enough space — ≈${spaceNeed().toFixed(1)} m² of furniture + people-space ` +
          `now exceeds the ≈${usableArea().toFixed(1)} m² usable in this ${$('rbWidth').value}×` +
          `${$('rbDepth').value} m room. Remove items or enlarge the room.`, 'bad');
      }
    });

    // resizing the room moves the budget — keep the m² counter honest
    ['rbWidth', 'rbDepth'].forEach((id) => $(id).addEventListener('input', updateTotal));

    $('pickerDone').onclick = closePicker;
    $('pickerClose').onclick = closePicker;
    $('picker').addEventListener('click', (e) => { if (e.target.id === 'picker') closePicker(); });

    const dz = $('rbDropzone'), gf = $('rbGenFile');
    dz.addEventListener('click', () => gf.click());
    gf.addEventListener('change', () => { if (gf.files[0]) uploadGenerated(gf.files[0]); gf.value = ''; });
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'dragend'].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove('drag')));
    dz.addEventListener('drop', (e) => {
      e.preventDefault(); dz.classList.remove('drag');
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) uploadGenerated(f);
    });

    $('rbAddCol').onclick = () => {
      const s = +$('rbColS').value || 0.4;
      obstacles.push({ x: +$('rbColX').value, z: +$('rbColZ').value, width: s, depth: s, kind: 'column' });
      renderChips();
    };
    $('rbAddDoor').onclick = () => {
      doors.push({ x: +$('rbDoorX').value, z: +$('rbDoorZ').value, width: +$('rbDoorW').value || 0.9, depth: 0.9 });
      renderChips();
    };

    $('rbGenerate').onclick = generate;
    $('rbReset').onclick = reset;
    $('expCsv').onclick = exportCsv;
    $('expGlb').onclick = exportGlb;
    $('expIfc').onclick = exportIfc;
    $('wallsBtn').onclick = toggleWalls;
    $('imgviewBtn').onclick = () => showImage($('vfallback').hidden);
  }

  window.roomBuilder = { ensureInit, applyResult, reloadScene, refreshCategoryBrowse,
                         hasScene: () => !!roomModel };
})();
