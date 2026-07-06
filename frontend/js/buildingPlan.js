/**
 * buildingPlan — the 2D floor plan of ONE building storey.
 *
 * Draws the selected floor's real rooms (from the IFC), their labeled fixed
 * elements (walls / columns / beams / stairs, door keep-clears) and every
 * furniture piece on that floor. Drag a piece to move it — collision against
 * other pieces, fixed elements and room boundaries is live (red = refused) —
 * and the 3D view updates instantly. 💾 Save layout persists the moves.
 *
 * Coordinates: IFC plan frame (x right, y away). Viewer world is Y-up with
 * z = -y_ifc, so a piece's plan position is (pos[0], -pos[2]).
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const viewer = () => window.xeokitModule && window.xeokitModule.getViewer && window.xeokitModule.getViewer();

  let canvas = null, ctx = null, open = false;
  let data = null;                     // {storey, rooms, pieces} from buildingMode
  let selected = null, dragging = false, dragOff = [0, 0], dragOK = true;
  const lastLegal = {};                // piece id -> [x, y] last legal plan spot
  let view = { s: 40, ox: 0, oy: 0, minx: 0, miny: 0 };

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);

  const KIND_FILL = {
    wall: '#5a6170', column: '#475266', beam: '#98a1b3',
    stair: '#7a8496', railing: '#aab3c2', fixed: '#8a93a5',
  };
  const CAT_FILL = {
    bed: '#7a9e7e', sofa: '#5d7a9e', desk: '#a97e4f', table: '#a97e4f',
    cabinet: '#8d8d95', bookshelf: '#8d6e5c', office_chair: '#3c4454',
    chair: '#3c4454', lamp: '#c9b458', stool: '#6e5c4f',
  };

  // ------------------------------------------------------------------ geometry
  function planPos(p) { return [p.pos[0], -p.pos[2]]; }
  function pieceRect(p) {
    const [x, y] = planPos(p);
    const w = (p.dims && p.dims[0]) || 0.6;
    const d = (p.dims && p.dims[1]) || 0.6;
    return [x - w / 2, y - d / 2, w, d];
  }
  function overlap(a, b) {
    return Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]) > 0.02 &&
           Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]) > 0.02;
  }
  function worldObstacles() {
    const out = [];
    (data.rooms || []).forEach((r) => {
      (r.obstacles || []).forEach((ob) => {
        out.push({ rect: [r.rect[0] + ob.x, r.rect[1] + ob.z, ob.width, ob.depth],
                   kind: ob.kind || 'fixed' });
      });
    });
    return out;
  }
  function isLegal(pid) {
    const p = data.pieces[pid];
    const r = pieceRect(p);
    // inside SOME room on this floor
    const inRoom = (data.rooms || []).some((rm) =>
      r[0] >= rm.rect[0] - 0.01 && r[1] >= rm.rect[1] - 0.01 &&
      r[0] + r[2] <= rm.rect[0] + rm.rect[2] + 0.01 &&
      r[1] + r[3] <= rm.rect[1] + rm.rect[3] + 0.01);
    if (!inRoom) return false;
    for (const [oid, o] of Object.entries(data.pieces)) {
      if (oid !== pid && overlap(r, pieceRect(o))) return false;
    }
    for (const ob of worldObstacles()) {
      if (overlap(r, ob.rect)) return false;
    }
    return true;
  }

  // ------------------------------------------------------------------ view
  function fitView() {
    const rooms = data.rooms || [];
    if (!rooms.length) return;
    const minx = Math.min(...rooms.map((r) => r.rect[0]));
    const miny = Math.min(...rooms.map((r) => r.rect[1]));
    const maxx = Math.max(...rooms.map((r) => r.rect[0] + r.rect[2]));
    const maxy = Math.max(...rooms.map((r) => r.rect[1] + r.rect[3]));
    const M = 50;
    view.s = Math.min((canvas.width - 2 * M) / (maxx - minx), (canvas.height - 2 * M) / (maxy - miny));
    view.minx = minx; view.miny = miny;
    view.ox = (canvas.width - (maxx - minx) * view.s) / 2;
    view.oy = (canvas.height - (maxy - miny) * view.s) / 2;
  }
  const X = (x) => view.ox + (x - view.minx) * view.s;
  const Y = (y) => view.oy + (y - view.miny) * view.s;

  // ------------------------------------------------------------------ draw
  function draw() {
    if (!ctx || !data) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f4f6fb';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    fitView();

    (data.rooms || []).forEach((r) => {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(X(r.rect[0]), Y(r.rect[1]), r.rect[2] * view.s, r.rect[3] * view.s);
      ctx.strokeStyle = '#1f2733'; ctx.lineWidth = 2.5;
      ctx.strokeRect(X(r.rect[0]), Y(r.rect[1]), r.rect[2] * view.s, r.rect[3] * view.s);
      ctx.fillStyle = '#6b7688'; ctx.font = 'bold 12px Segoe UI';
      ctx.fillText(`${r.name} · ${r.area} m²`, X(r.rect[0]) + 6, Y(r.rect[1]) + 16);
    });

    worldObstacles().forEach((ob) => {
      if (ob.kind === 'door') {
        ctx.fillStyle = 'rgba(53,120,229,0.22)';
        ctx.fillRect(X(ob.rect[0]), Y(ob.rect[1]), ob.rect[2] * view.s, ob.rect[3] * view.s);
        ctx.fillStyle = '#3578e5'; ctx.font = '9px Segoe UI';
        ctx.fillText('door', X(ob.rect[0]) + 2, Y(ob.rect[1]) + 10);
      } else {
        ctx.fillStyle = KIND_FILL[ob.kind] || KIND_FILL.fixed;
        ctx.fillRect(X(ob.rect[0]), Y(ob.rect[1]), ob.rect[2] * view.s, ob.rect[3] * view.s);
      }
    });

    Object.entries(data.pieces || {}).forEach(([pid, p]) => {
      const r = pieceRect(p);
      const sel = selected === pid;
      const bad = sel && dragging && !dragOK;
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = bad ? '#e05a5a' : (CAT_FILL[p.category] || '#7d8aa0');
      ctx.fillRect(X(r[0]), Y(r[1]), r[2] * view.s, r[3] * view.s);
      ctx.globalAlpha = 1;
      ctx.lineWidth = sel ? 3 : 1;
      ctx.strokeStyle = bad ? '#a11d1d' : sel ? '#2f6bff' : '#1f2733';
      ctx.strokeRect(X(r[0]), Y(r[1]), r[2] * view.s, r[3] * view.s);
      ctx.fillStyle = '#1f2733'; ctx.font = `${sel ? 'bold ' : ''}10px Segoe UI`;
      ctx.fillText(p.category.replace(/_/g, ' '), X(r[0]), Y(r[1]) - 3);
    });

    ctx.fillStyle = '#6b7688'; ctx.font = 'bold 13px Segoe UI';
    ctx.fillText(data.storey ? `▤ ${data.storey.name}` : 'Floor plan', 16, 24);
  }

  // ------------------------------------------------------------------ input
  function toPlan(e) {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) * (canvas.width / r.width) - view.ox) / view.s + view.minx,
            ((e.clientY - r.top) * (canvas.height / r.height) - view.oy) / view.s + view.miny];
  }
  function pick(mx, my) {
    for (const [pid, p] of Object.entries(data.pieces || {})) {
      const r = pieceRect(p);
      if (mx >= r[0] && mx <= r[0] + r[2] && my >= r[1] && my <= r[1] + r[3]) return pid;
    }
    return null;
  }
  function movePiece(pid, nx, ny) {
    const p = data.pieces[pid];
    p.pos[0] = Math.round(nx * 100) / 100;
    p.pos[2] = -Math.round(ny * 100) / 100;
    try { p.model.position = p.pos; } catch (e) {}
    dragOK = isLegal(pid);
    draw();
  }

  // ------------------------------------------------------------------ open/close
  function toggle(force) {
    open = force !== undefined ? force : !open;
    if (open && (!window.buildingMode || !window.buildingMode.hasContent())) {
      banner('Populate the building first — then explore it floor by floor.', true);
      open = false;
    }
    $('bplanWrap').hidden = !open;          // unhide FIRST — a hidden wrap measures 0×0
    $('bPlanBtn').textContent = open ? '🧊 3D view' : '🗺️ 2D floor';
    if (open) {
      // 2D needs one specific floor — auto-pick the first if viewing "All"
      if (!window.buildingMode.currentFloor()) {
        const fd = window.buildingMode.getFloorData();
        if (fd.storey) window.buildingMode.selectFloor(fd.storey.name);
      }
      data = window.buildingMode.getFloorData();
      resize();
      draw();
    }
  }

  function floorChanged() {
    if (!open) return;
    data = window.buildingMode.getFloorData();
    selected = null;
    draw();
  }

  function resize() {
    const wrap = $('bplanWrap');
    canvas.width = wrap.clientWidth;
    canvas.height = wrap.clientHeight;
  }

  // ------------------------------------------------------------------ wiring
  document.addEventListener('DOMContentLoaded', () => {
    canvas = $('bplanCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    $('bPlanBtn').addEventListener('click', () => toggle());
    window.addEventListener('resize', () => { if (open) { resize(); draw(); } });

    canvas.addEventListener('pointerdown', (e) => {
      const [mx, my] = toPlan(e);
      selected = pick(mx, my);
      if (selected) {
        const p = data.pieces[selected];
        const [px, py] = planPos(p);
        lastLegal[selected] = lastLegal[selected] || [px, py];
        dragging = true;
        dragOff = [mx - px, my - py];
        canvas.setPointerCapture(e.pointerId);
      }
      draw();
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!dragging || !selected) return;
      const [mx, my] = toPlan(e);
      movePiece(selected, mx - dragOff[0], my - dragOff[1]);
    });
    const drop = () => {
      if (!dragging || !selected) { dragging = false; return; }
      dragging = false;
      if (!dragOK) {
        banner('No room there — put it somewhere clear.', true);
        const back = lastLegal[selected];
        movePiece(selected, back[0], back[1]);
        dragOK = true;
      } else {
        lastLegal[selected] = planPos(data.pieces[selected]);
        window.buildingMode.refreshPiece(selected);   // reload GLB at final spot
        banner('Moved. Drag more, or 💾 Save layout to keep everything.');
      }
      draw();
    };
    canvas.addEventListener('pointerup', drop);
    canvas.addEventListener('pointercancel', drop);
  });

  window.buildingPlan = { toggle, isOpen: () => open, floorChanged };
})();
