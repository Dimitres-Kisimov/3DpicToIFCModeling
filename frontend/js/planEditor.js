/**
 * planEditor — the 2D floor plan: the authoritative MANUAL placement surface.
 *
 * Top-down canvas over the 3D stage. Draws the true room (walls, columns, beams,
 * door clearances), every furniture footprint with its interaction-zone halo, and
 * lets the user drag each piece to its EXACT spot (or type exact X/Z/rotation).
 * Collision is checked LIVE while dragging — against other furniture, building
 * obstacles and interaction zones; illegal spots show red and refuse the drop.
 *
 * Every committed move updates the shared model: the 3D view shifts instantly
 * (entity offsets), and the server re-validates (overlaps + circulation) and
 * rewrites schedule.json + scene.ifc — so exports always match the manual truth.
 * Moving a parent takes its anchored children (chair, monitor) along with it.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();

  let canvas = null, ctx = null, open = false;
  let room = null;                 // {width, depth, obstacles[], doors[]}
  let items = [];                  // [{id,name,x,z,rot,w,d,hex,elevation,anchor_to}]
  let zones = {};                  // id -> [[x0,z0,w,d]]
  let basePos = {};                // id -> [x,z] as baked into the loaded GLB
  let selected = null, dragging = false, dragOff = [0, 0], dragOK = true;
  let snap = true;
  let violations = new Set();      // item ids currently in violation (server verdict)
  let view = { s: 50, ox: 0, oz: 0 };   // px per metre + canvas offset

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);

  // ------------------------------------------------------------------ data in
  function setData(result) {
    room = JSON.parse(JSON.stringify(result.room || {}));
    room.obstacles = room.obstacles || [];
    room.doors = room.doors || [];
    zones = JSON.parse(JSON.stringify(result.zones || {}));
    items = (result.items || []).map((it) => ({
      id: it.id, name: it.name, x: +it.x, z: +it.z,
      rot: +(it.rotation_deg || 0), w: +it.width_m, d: +it.depth_m,
      hex: it.material_hex || '#8899aa', elevation: +(it.elevation || 0),
      anchor_to: it.anchor_to || null,
    }));
    basePos = {};
    items.forEach((it) => { basePos[it.id] = [it.x, it.z]; });
    selected = null;
    violations.clear();
    if (open) draw();
  }

  // ------------------------------------------------------------------ geometry
  function footRect(it) {
    let w = it.w, d = it.d;
    if (Math.round(it.rot / 90) % 2) { const t = w; w = d; d = t; }
    return [it.x - w / 2, it.z - d / 2, w, d];
  }
  function overlap(a, b) {
    return Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]) > 0.02 &&
           Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]) > 0.02;
  }
  function children(id) { return items.filter((c) => c.anchor_to === id); }

  function isLegal(it) {
    const r = footRect(it);
    if (r[0] < 0 || r[1] < 0 || r[0] + r[2] > room.width || r[1] + r[3] > room.depth) return false;
    const clan = new Set([it.id, it.anchor_to, ...children(it.id).map((c) => c.id)]);
    for (const o of items) {
      if (clan.has(o.id) || o.elevation > 0.01) continue;
      if (overlap(r, footRect(o))) return false;
      for (const z of (zones[o.id] || [])) if (overlap(r, z)) return false;
    }
    for (const ob of room.obstacles) {
      if (overlap(r, [+ob.x, +ob.z, +ob.width, +ob.depth])) return false;
    }
    for (const dr of room.doors) {
      if (overlap(r, [+dr.x, +dr.z, +dr.width, +(dr.depth || dr.width)])) return false;
    }
    return true;
  }

  // ------------------------------------------------------------------ drawing
  function fitView() {
    const W = canvas.width, H = canvas.height, M = 46;
    view.s = Math.min((W - 2 * M) / room.width, (H - 2 * M) / room.depth);
    view.ox = (W - room.width * view.s) / 2;
    view.oz = (H - room.depth * view.s) / 2;
  }
  const X = (x) => view.ox + x * view.s;
  const Z = (z) => view.oz + z * view.s;

  function draw() {
    if (!ctx || !room) return;
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(244,246,251,0.97)';
    ctx.fillRect(0, 0, W, H);
    fitView();

    // room + grid
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(X(0), Z(0), room.width * view.s, room.depth * view.s);
    ctx.strokeStyle = '#eef1f7'; ctx.lineWidth = 1;
    for (let gx = 0.5; gx < room.width; gx += 0.5) {
      ctx.beginPath(); ctx.moveTo(X(gx), Z(0)); ctx.lineTo(X(gx), Z(room.depth)); ctx.stroke();
    }
    for (let gz = 0.5; gz < room.depth; gz += 0.5) {
      ctx.beginPath(); ctx.moveTo(X(0), Z(gz)); ctx.lineTo(X(room.width), Z(gz)); ctx.stroke();
    }
    ctx.strokeStyle = '#1f2733'; ctx.lineWidth = 3;
    ctx.strokeRect(X(0), Z(0), room.width * view.s, room.depth * view.s);

    // doors (egress, kept clear) + obstacles (building keep-outs)
    room.doors.forEach((dr) => {
      ctx.fillStyle = 'rgba(53,120,229,0.25)';
      ctx.fillRect(X(+dr.x), Z(+dr.z), +dr.width * view.s, +(dr.depth || dr.width) * view.s);
      ctx.fillStyle = '#3578e5'; ctx.font = '10px Segoe UI';
      ctx.fillText('door', X(+dr.x) + 3, Z(+dr.z) + 12);
    });
    room.obstacles.forEach((ob) => {
      ctx.fillStyle = '#5a6170';
      ctx.fillRect(X(+ob.x), Z(+ob.z), +ob.width * view.s, +ob.depth * view.s);
      ctx.fillStyle = '#fff'; ctx.font = '9px Segoe UI';
      ctx.fillText(ob.kind || 'column', X(+ob.x) + 2, Z(+ob.z) + 10);
    });

    // interaction-zone halos (people space)
    for (const [id, zr] of Object.entries(zones)) {
      const sel = selected && selected.id === id;
      ctx.fillStyle = sel ? 'rgba(31,170,96,0.30)' : 'rgba(31,170,96,0.15)';
      ctx.strokeStyle = 'rgba(31,170,96,0.5)';
      ctx.setLineDash([4, 3]);
      zr.forEach(([zx, zz, zw, zd]) => {
        ctx.fillRect(X(zx), Z(zz), zw * view.s, zd * view.s);
        ctx.strokeRect(X(zx), Z(zz), zw * view.s, zd * view.s);
      });
      ctx.setLineDash([]);
    }

    // furniture footprints
    items.forEach((it) => {
      const [rx, rz, rw, rd] = footRect(it);
      const sel = selected && selected.id === it.id;
      const bad = (sel && dragging && !dragOK) || violations.has(it.id);
      const onTop = it.elevation > 0.01;
      ctx.globalAlpha = onTop ? 0.55 : 0.9;
      ctx.fillStyle = bad ? '#e05a5a' : it.hex;
      ctx.fillRect(X(rx), Z(rz), rw * view.s, rd * view.s);
      ctx.globalAlpha = 1;
      ctx.lineWidth = sel ? 3 : 1.2;
      ctx.strokeStyle = bad ? '#a11d1d' : sel ? '#2f6bff' : '#1f2733';
      if (onTop) ctx.setLineDash([3, 3]);
      ctx.strokeRect(X(rx), Z(rz), rw * view.s, rd * view.s);
      ctx.setLineDash([]);
      // facing tick (front side)
      const th = (it.rot * Math.PI) / 180;
      const fx = Math.sin(th), fz = Math.cos(th);
      ctx.strokeStyle = sel ? '#2f6bff' : '#475266'; ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(X(it.x), Z(it.z));
      ctx.lineTo(X(it.x + fx * (Math.abs(fx) > 0.5 ? rw : rd) * 0.5),
                 Z(it.z + fz * (Math.abs(fz) > 0.5 ? rd : rw) * 0.5));
      ctx.stroke();
      // label
      ctx.fillStyle = '#1f2733'; ctx.font = `${sel ? 'bold ' : ''}11px Segoe UI`;
      ctx.fillText(it.name, X(rx) + 3, Z(rz) - 4);
    });

    // dimensions
    ctx.fillStyle = '#6b7688'; ctx.font = '11px Segoe UI';
    ctx.fillText(`${room.width} m`, X(room.width / 2) - 12, Z(room.depth) + 26);
    ctx.save();
    ctx.translate(X(0) - 26, Z(room.depth / 2));
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(`${room.depth} m`, -12, 0);
    ctx.restore();
  }

  // ------------------------------------------------------------------ 3D sync
  function sync3D(ids) {
    const v = viewer();
    if (!v) return;
    (ids || items.map((i) => i.id)).forEach((id) => {
      const it = items.find((i) => i.id === id);
      const ent = v.scene.objects[id];
      const base = basePos[id];
      if (it && ent && base) {
        try { ent.offset = [it.x - base[0], 0, it.z - base[1]]; } catch (e) {}
      }
    });
  }

  let saveTimer = null;
  function persist(rebuild) {
    // debounce a burst of drags into one server round-trip
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const positions = {};
      items.forEach((it) => { positions[it.id] = { x: it.x, z: it.z, rotation_deg: it.rot }; });
      try {
        const r = await fetch('/api/room/positions', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ positions, rebuild: !!rebuild }),
        });
        const d = await r.json();
        if (!d.ok) { banner('Save failed: ' + (d.error || '?'), true); return; }
        zones = d.zones || zones;
        violations = new Set((d.violations || []).flatMap((v2) => [v2.a]));
        if (d.circulation && !d.circulation.ok) {
          banner(`⚠ ${d.circulation.unreachable.join(', ')} now hard to reach — leave an aisle.`, true);
        } else if (violations.size) {
          banner('⚠ Overlap detected — the red item needs a new spot.', true);
        }
        if (rebuild && window.roomBuilder) {
          // rotation changed geometry -> reload the room GLB (fresh node positions)
          window.roomBuilder.reloadScene();
          items.forEach((it) => { basePos[it.id] = [it.x, it.z]; });
        }
        draw();
      } catch (e) { banner('Save failed: ' + e, true); }
    }, 350);
  }

  // ------------------------------------------------------------------ input
  function pick(mx, mz) {
    // topmost first: on-top items, then floor items
    const hit = (it) => {
      const [rx, rz, rw, rd] = footRect(it);
      return mx >= rx && mx <= rx + rw && mz >= rz && mz <= rz + rd;
    };
    return items.filter((i) => i.elevation > 0.01).find(hit) ||
           items.filter((i) => i.elevation <= 0.01).find(hit) || null;
  }

  function toRoom(e) {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) * (canvas.width / r.width) - view.ox) / view.s,
            ((e.clientY - r.top) * (canvas.height / r.height) - view.oz) / view.s];
  }

  function moveSelected(nx, nz) {
    if (!selected) return;
    if (snap) { nx = Math.round(nx * 10) / 10; nz = Math.round(nz * 10) / 10; }
    const dx = nx - selected.x, dz = nz - selected.z;
    const group = [selected, ...children(selected.id)];
    group.forEach((g) => { g.x = Math.round((g.x + dx) * 1000) / 1000; g.z = Math.round((g.z + dz) * 1000) / 1000; });
    (zones[selected.id] || []).forEach((zr) => { zr[0] += dx; zr[1] += dz; });
    group.slice(1).forEach((g) => (zones[g.id] || []).forEach((zr) => { zr[0] += dx; zr[1] += dz; }));
    dragOK = isLegal(selected);
    sync3D(group.map((g) => g.id));
    updateInspector();
    draw();
  }

  function rotateSelected() {
    if (!selected) return;
    selected.rot = (selected.rot + 90) % 360;
    // zones rotate server-side on persist; approximate locally by clearing halo
    delete zones[selected.id];
    dragOK = isLegal(selected);
    updateInspector();
    draw();
    persist(true);          // rotation changes geometry -> rebuild + reload GLB
  }

  // ------------------------------------------------------------------ inspector
  function updateInspector() {
    const box = $('planInspector');
    if (!box) return;
    if (!selected) { box.hidden = true; return; }
    box.hidden = false;
    $('piName').textContent = selected.name;
    $('piX').value = selected.x.toFixed(2);
    $('piZ').value = selected.z.toFixed(2);
    $('piRot').value = selected.rot;
  }

  function applyInspector() {
    if (!selected) return;
    const nx = parseFloat($('piX').value), nz = parseFloat($('piZ').value);
    const nr = ((parseInt($('piRot').value, 10) || 0) % 360 + 360) % 360;
    const rotChanged = nr !== selected.rot;
    if (rotChanged) { selected.rot = nr; delete zones[selected.id]; }
    if (!Number.isNaN(nx) && !Number.isNaN(nz)) moveSelected(nx, nz);
    if (!isLegal(selected)) {
      banner('That exact spot collides — pick a clear one.', true);
    }
    persist(rotChanged);
  }

  // ------------------------------------------------------------------ open/close
  function toggle(force) {
    open = force !== undefined ? force : !open;
    $('planWrap').hidden = !open;
    $('planBtn').textContent = open ? '🧊 3D view' : '🗺️ 2D plan';
    if (open) {
      if (!room) { banner('Generate a layout first — then fine-tune it here.', true); toggle(false); return; }
      resize();
      draw();
    }
    updateInspector();
  }

  function resize() {
    const wrap = $('planWrap');
    canvas.width = wrap.clientWidth;
    canvas.height = wrap.clientHeight;
  }

  // ------------------------------------------------------------------ wiring
  document.addEventListener('DOMContentLoaded', () => {
    canvas = $('planCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    $('planBtn').addEventListener('click', () => toggle());
    window.addEventListener('resize', () => { if (open) { resize(); draw(); } });

    canvas.addEventListener('pointerdown', (e) => {
      const [mx, mz] = toRoom(e);
      selected = pick(mx, mz);
      if (selected) {
        dragging = true;
        dragOff = [mx - selected.x, mz - selected.z];
        canvas.setPointerCapture(e.pointerId);
      }
      updateInspector();
      draw();
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!dragging || !selected) return;
      const [mx, mz] = toRoom(e);
      moveSelected(mx - dragOff[0], mz - dragOff[1]);
    });
    const drop = () => {
      if (!dragging || !selected) { dragging = false; return; }
      dragging = false;
      if (!dragOK) {
        // refuse the drop: snap the whole group back to its last legal spot
        banner('No room there — put it somewhere clear.', true);
        const back = basePosSafe(selected);
        moveSelected(back[0], back[1]);
        dragOK = true;
        draw();
        return;
      }
      lastLegal[selected.id] = [selected.x, selected.z];
      persist(false);
    };
    canvas.addEventListener('pointerup', drop);
    canvas.addEventListener('pointercancel', drop);

    document.addEventListener('keydown', (e) => {
      if (!open || !selected) return;
      if (e.key === 'r' || e.key === 'R') { e.preventDefault(); rotateSelected(); }
    });

    $('piApply').addEventListener('click', applyInspector);
    $('piRotate').addEventListener('click', rotateSelected);
    $('piSnap').addEventListener('change', (e) => { snap = e.target.checked; });
  });

  const lastLegal = {};
  function basePosSafe(it) {
    return lastLegal[it.id] || basePos[it.id] || [it.x, it.z];
  }

  window.planEditor = { setData, toggle, isOpen: () => open };
})();
