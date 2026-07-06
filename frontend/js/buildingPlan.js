/**
 * buildingPlan — the 2D floor plan of ONE building storey.
 *
 * Draws the WHOLE floor as one connected apartment: furnishable rooms in full,
 * context spaces (foyer / hallway / stair / bath) lightly, fixed elements
 * (walls / columns / beams) clipped to their rooms and toned down, door
 * clearances, and every furniture piece as a labeled footprint.
 *
 * Interactions:
 *   · drag a piece  — live collision (shared clash engine in buildingMode);
 *                     illegal drops snap back; the 3D updates instantly
 *   · click a room  — see everything in it + "🧊 Enter room" teleports the 3D
 *                     camera inside it (double-click jumps straight in)
 *   · clashing pieces stay outlined red until resolved (🧹 or by hand)
 *
 * Coordinates: IFC plan frame (x right, y away); viewer world z = -y_ifc.
 */
(function () {
  const $ = (id) => document.getElementById(id);

  let canvas = null, ctx = null, open = false;
  let data = null;                     // {storey, rooms, pieces} from buildingMode
  let selected = null, dragging = false, dragOff = [0, 0], dragOK = true;
  let selectedRoom = null;
  let clashes = new Set();
  const lastLegal = {};                // piece id -> [x, y] last legal plan spot
  let view = { s: 40, ox: 0, oy: 0, minx: 0, miny: 0 };

  const banner = (t, bad) => window.appShell && window.appShell.banner(t, bad);
  const bm = () => window.buildingMode;

  const KIND_FILL = {
    wall: 'rgba(90,97,112,0.55)', column: 'rgba(71,82,102,0.75)', beam: 'rgba(152,161,179,0.45)',
    stair: 'rgba(122,132,150,0.45)', railing: 'rgba(170,179,194,0.45)', fixed: 'rgba(138,147,165,0.5)',
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
  function clipRect(r, b) {
    const x0 = Math.max(r[0], b[0]), y0 = Math.max(r[1], b[1]);
    const x1 = Math.min(r[0] + r[2], b[0] + b[2]), y1 = Math.min(r[1] + r[3], b[1] + b[3]);
    return (x1 - x0 > 0.01 && y1 - y0 > 0.01) ? [x0, y0, x1 - x0, y1 - y0] : null;
  }
  function piecesInRoom(room) {
    return Object.entries(data.pieces || {}).filter(([, p]) => {
      const [x, y] = planPos(p);
      return x >= room.rect[0] && x <= room.rect[0] + room.rect[2] &&
             y >= room.rect[1] && y <= room.rect[1] + room.rect[3];
    });
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
    clashes = bm().findClashes();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f4f6fb';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    fitView();

    const rooms = data.rooms || [];
    // context spaces first (light), then furnishable rooms on top
    const ordered = [...rooms.filter((r) => r.furnishable === false),
                     ...rooms.filter((r) => r.furnishable !== false)];
    ordered.forEach((r) => {
      const furn = r.furnishable !== false;
      const sel = selectedRoom && selectedRoom === r;
      ctx.fillStyle = sel ? '#eef4ff' : furn ? '#ffffff' : '#f0f2f7';
      ctx.fillRect(X(r.rect[0]), Y(r.rect[1]), r.rect[2] * view.s, r.rect[3] * view.s);
      ctx.strokeStyle = sel ? '#2f6bff' : furn ? '#1f2733' : '#b9c1cf';
      ctx.lineWidth = sel ? 3 : furn ? 2 : 1.2;
      if (!furn) ctx.setLineDash([5, 4]);
      ctx.strokeRect(X(r.rect[0]), Y(r.rect[1]), r.rect[2] * view.s, r.rect[3] * view.s);
      ctx.setLineDash([]);
      ctx.fillStyle = furn ? (sel ? '#1f52d6' : '#3c4454') : '#9aa3b2';
      ctx.font = `${furn ? 'bold ' : ''}${furn ? 12 : 10}px Segoe UI`;
      ctx.fillText(furn ? `${r.name} · ${r.area} m²` : r.name,
                   X(r.rect[0]) + 5, Y(r.rect[1]) + 14);
    });

    // fixed elements — clipped to their room, toned down so the PLAN stays readable
    rooms.forEach((r) => {
      (r.obstacles || []).forEach((ob) => {
        const world = [r.rect[0] + ob.x, r.rect[1] + ob.z, ob.width, ob.depth];
        const c = clipRect(world, r.rect);
        if (!c) return;
        if (ob.kind === 'door') {
          ctx.fillStyle = 'rgba(53,120,229,0.18)';
          ctx.fillRect(X(c[0]), Y(c[1]), c[2] * view.s, c[3] * view.s);
        } else {
          ctx.fillStyle = KIND_FILL[ob.kind] || KIND_FILL.fixed;
          ctx.fillRect(X(c[0]), Y(c[1]), c[2] * view.s, c[3] * view.s);
        }
      });
    });

    // furniture pieces
    Object.entries(data.pieces || {}).forEach(([pid, p]) => {
      const r = pieceRect(p);
      const sel = selected === pid;
      const bad = clashes.has(pid) || (sel && dragging && !dragOK);
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = bad ? '#e05a5a' : (CAT_FILL[p.category] || '#7d8aa0');
      ctx.fillRect(X(r[0]), Y(r[1]), r[2] * view.s, r[3] * view.s);
      ctx.globalAlpha = 1;
      ctx.lineWidth = sel || bad ? 3 : 1;
      ctx.strokeStyle = bad ? '#a11d1d' : sel ? '#2f6bff' : '#1f2733';
      ctx.strokeRect(X(r[0]), Y(r[1]), r[2] * view.s, r[3] * view.s);
      ctx.fillStyle = bad ? '#a11d1d' : '#1f2733';
      ctx.font = `${sel ? 'bold ' : ''}10px Segoe UI`;
      ctx.fillText(p.category.replace(/_/g, ' '), X(r[0]), Y(r[1]) - 3);
    });

    ctx.fillStyle = '#6b7688'; ctx.font = 'bold 13px Segoe UI';
    const nClash = clashes.size;
    ctx.fillText((data.storey ? `▤ ${data.storey.name}` : 'Floor plan')
      + (nClash ? `   ·   ⚠ ${nClash} clash${nClash === 1 ? '' : 'es'} (red)` : ''), 16, 24);
  }

  // ------------------------------------------------------------------ room info
  function showRoomInfo(room) {
    const box = $('bRoomInfo');
    if (!room) { box.hidden = true; return; }
    box.hidden = false;
    $('bRoomTitle').textContent = `${room.name} · ${room.area} m²`;
    const list = $('bRoomItems');
    list.innerHTML = '';
    const inside = piecesInRoom(room);
    if (!inside.length) {
      list.innerHTML = '<li class="mut">nothing placed here</li>';
    } else {
      inside.forEach(([pid, p]) => {
        const li = document.createElement('li');
        li.textContent = p.category.replace(/_/g, ' ');
        if (clashes.has(pid)) { li.textContent += ' ⚠'; li.style.color = '#a11d1d'; }
        list.appendChild(li);
      });
    }
    $('bRoomEnter').onclick = () => bm().enterRoom(room);
  }

  // ------------------------------------------------------------------ input
  function toPlan(e) {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) * (canvas.width / r.width) - view.ox) / view.s + view.minx,
            ((e.clientY - r.top) * (canvas.height / r.height) - view.oy) / view.s + view.miny];
  }
  function pickPiece(mx, my) {
    for (const [pid, p] of Object.entries(data.pieces || {})) {
      const r = pieceRect(p);
      if (mx >= r[0] && mx <= r[0] + r[2] && my >= r[1] && my <= r[1] + r[3]) return pid;
    }
    return null;
  }
  function pickRoom(mx, my) {
    // furnishable rooms take priority over overlapping context spaces
    const hit = (r) => mx >= r.rect[0] && mx <= r.rect[0] + r.rect[2] &&
                       my >= r.rect[1] && my <= r.rect[1] + r.rect[3];
    return (data.rooms || []).filter((r) => r.furnishable !== false).find(hit) ||
           (data.rooms || []).find(hit) || null;
  }
  function movePiece(pid, nx, ny) {
    const p = data.pieces[pid];
    p.pos[0] = Math.round(nx * 100) / 100;
    p.pos[2] = -Math.round(ny * 100) / 100;
    try { p.model.position = p.pos; } catch (e) {}
    dragOK = bm().isLegalPiece(pid);
    draw();
  }

  // ------------------------------------------------------------------ open/close
  function toggle(force) {
    open = force !== undefined ? force : !open;
    if (open && (!bm() || !bm().hasContent())) {
      banner('Populate the building first — then explore it floor by floor.', true);
      open = false;
    }
    $('bplanWrap').hidden = !open;          // unhide FIRST — a hidden wrap measures 0×0
    $('bPlanBtn').textContent = open ? '🧊 3D view' : '🗺️ 2D floor';
    if (open) {
      if (!bm().currentFloor()) {
        const fd = bm().getFloorData();
        if (fd.storey) bm().selectFloor(fd.storey.name);
      }
      data = bm().getFloorData();
      resize();
      draw();
    } else {
      selectedRoom = null;
      showRoomInfo(null);
    }
  }

  function floorChanged() {
    if (!open) return;
    data = bm().getFloorData();
    selected = null;
    selectedRoom = null;
    showRoomInfo(null);
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
    $('bRoomClose').addEventListener('click', () => { selectedRoom = null; showRoomInfo(null); draw(); });
    window.addEventListener('resize', () => { if (open) { resize(); draw(); } });

    canvas.addEventListener('pointerdown', (e) => {
      const [mx, my] = toPlan(e);
      selected = pickPiece(mx, my);
      if (selected) {
        const p = data.pieces[selected];
        const [px, py] = planPos(p);
        if (!lastLegal[selected] && bm().isLegalPiece(selected)) lastLegal[selected] = [px, py];
        dragging = true;
        dragOff = [mx - px, my - py];
        canvas.setPointerCapture(e.pointerId);
        selectedRoom = null;
        showRoomInfo(null);
      } else {
        selectedRoom = pickRoom(mx, my);
        showRoomInfo(selectedRoom);
      }
      draw();
    });
    canvas.addEventListener('dblclick', (e) => {
      const [mx, my] = toPlan(e);
      if (pickPiece(mx, my)) return;
      const room = pickRoom(mx, my);
      if (room) bm().enterRoom(room);
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
        if (back) movePiece(selected, back[0], back[1]);
        dragOK = true;
      } else {
        lastLegal[selected] = planPos(data.pieces[selected]);
        bm().refreshPiece(selected);         // reload GLB at the final spot
        banner('Moved. Drag more, or 💾 Save layout to keep everything.');
      }
      draw();
    };
    canvas.addEventListener('pointerup', drop);
    canvas.addEventListener('pointercancel', drop);
  });

  window.buildingPlan = { toggle, isOpen: () => open, floorChanged };
})();
