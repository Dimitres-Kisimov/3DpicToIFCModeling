import { Viewer, GLTFLoaderPlugin } from "/node_modules/@xeokit/xeokit-sdk/dist/xeokit-sdk.min.es.js";

const $ = (id) => document.getElementById(id);

// The 3D preview needs a WebGL context. If the browser can't give one (too many
// open 3D tabs hitting the context limit, or hardware acceleration off), keep the
// app fully usable for picking items + generating + IFC/CSV export — just no preview.
let viewer = null, cc = null, gltf = null;
try {
  viewer = new Viewer({ canvasId: "cv", transparent: false });
  viewer.camera.eye = [11, 8, 11];
  viewer.camera.look = [4, 0.5, 3];
  viewer.camera.up = [0, 1, 0];
  cc = viewer.cameraControl;
  cc.navMode = "orbit"; cc.followPointer = false;
  cc.rotationInertia = 0; cc.dollyInertia = 0; cc.panInertia = 0; cc.mouseWheelDollyRate = 30;
  gltf = new GLTFLoaderPlugin(viewer);
} catch (e) {
  console.error("WebGL viewer unavailable:", e);
  setTimeout(() => setMsg("Live 3D off (no WebGL) — a rendered image of the room will be shown after you Generate. Tip: close other tabs / enable hardware acceleration for the interactive 3D.", true), 0);
}
let model = null, wallsVisible = true, lastItems = [];
const counts = {};
const obstacles = [], doors = [];

loadCatalog();   // load items FIRST, before any handler wiring, so the list always populates

function setMsg(t, bad) { const m = $("msg"); m.textContent = t; m.className = bad ? "bad" : ""; }

// ⋯ pick button HTML for a category row. Shown when the category has ABO meshes OR
// at least one user-generated item, so generated-only categories are still browsable.
function browseBtnHTML(c) {
  const gen = c.generated_count || 0;
  if (!c.abo && !gen) return "";
  const label = c.abo ? `⋯ pick (${c.abo_count})` : "⋯ pick";
  const genTag = gen ? ` <span style="color:#f0a500">+${gen} ours</span>` : "";
  return `<button class="browse" data-browse="${c.category}">${label}${genTag}</button>`;
}

async function loadCatalog() {
  const cats = await (await fetch("/api/catalog")).json();
  const el = $("catalog");
  cats.forEach((c) => {
    counts[c.category] = 0;
    const row = document.createElement("div");
    row.className = "catrow";
    const browse = browseBtnHTML(c);
    row.innerHTML =
      `<span>${c.label} <small>${c.abo ? "· ABO" : "· prim"}</small></span>` +
      `<span class="step" id="step-${c.category}">${browse}<button data-c="${c.category}" data-d="-1">−</button>` +
      `<b id="n-${c.category}">0</b><button data-c="${c.category}" data-d="1">+</button></span>`;
    el.appendChild(row);
  });
  el.addEventListener("click", (e) => {
    const br = e.target.closest("button[data-browse]");
    if (br) { openPicker(br.dataset.browse); return; }
    const b = e.target.closest("button[data-c]"); if (!b) return;
    const c = b.dataset.c;
    counts[c] = Math.max(0, counts[c] + (+b.dataset.d));
    chosen[c] = [];                       // manual count overrides any specific picks
    $("n-" + c).textContent = counts[c];
    updateTotal();
  });
}

// ---------------------------------------------------------------------------
// Drop your OWN generated furniture (.glb / .ifc) in — it gets auto-categorized
// server-side and appears (badged "OURS") in that category's ⋯ picker.
// ---------------------------------------------------------------------------
async function uploadGenerated(file) {
  if (!file) return;
  const name = (file.name || "").toLowerCase();
  if (!name.endsWith(".glb") && !name.endsWith(".ifc")) {
    setMsg("Only .glb or .ifc files can be added.", true); return;
  }
  setMsg(`Uploading ${file.name}…`);
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/upload_generated", { method: "POST", body: fd });
    const d = await r.json();
    if (!d.ok) { setMsg("Upload failed: " + (d.error || "unknown"), true); return; }
    const cat = d.item.category;
    await refreshCategoryBrowse(cat);   // update/inject the ⋯ button (preserves counts)
    // The ⋯ picker re-fetches /api/items/<cat> each time it opens and now includes
    // generated items, so the new asset is immediately reachable. If that category's
    // picker is open right now, refresh it so the item appears at once.
    if (pickerCat === cat) openPicker(cat);
    setMsg(`Added to “${cat.replace(/_/g, " ")}” (generated) — open its ⋯ picker to select it.`);
  } catch (e) { setMsg("Upload error: " + e, true); }
}

// After an upload, re-fetch the catalog and update just this category's ⋯ button
// (bump its "+N ours" count, or inject the button if the category had none). Does
// NOT reset the count steppers, so any in-progress selection is preserved.
async function refreshCategoryBrowse(cat) {
  try {
    const cats = await (await fetch("/api/catalog")).json();
    const c = cats.find((x) => x.category === cat);
    if (!c) return;
    const step = $("step-" + cat);
    if (!step) return;
    const existing = step.querySelector("button[data-browse]");
    const html = browseBtnHTML(c);
    if (existing) existing.outerHTML = html;                 // replace with updated label
    else if (html) step.insertAdjacentHTML("afterbegin", html);   // inject where none existed
  } catch (e) { /* non-fatal — item is still reachable when the picker is opened */ }
}

{
  const dz = $("dropzone"), gf = $("genfile");
  if (dz && gf) {
    dz.addEventListener("click", () => gf.click());
    gf.addEventListener("change", () => { if (gf.files[0]) uploadGenerated(gf.files[0]); gf.value = ""; });
    ["dragenter", "dragover"].forEach((ev) =>
      dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "dragend"].forEach((ev) =>
      dz.addEventListener(ev, () => dz.classList.remove("drag")));
    dz.addEventListener("drop", (e) => {
      e.preventDefault(); dz.classList.remove("drag");
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) uploadGenerated(f);
    });
  }
}

// specific-mesh selection from the 400: chosen[category] = [ASIN, ...]
const chosen = {};
let pickerCat = null;

async function openPicker(category) {
  pickerCat = category;
  $("picker-title").textContent = "Choose " + category.replace("_", " ") + " — pick specific items";
  const grid = $("picker-grid"); grid.innerHTML = "Loading…";
  const items = await (await fetch("/api/items/" + category)).json();
  const sel = new Set(chosen[category] || []);
  grid.innerHTML = "";
  items.forEach((it) => {
    const d = it.dims_m || [];
    const dim = (d[0] != null) ? `${d[0]}×${d[1]}×${d[2]} m` : "";
    const cell = document.createElement("div");
    cell.className = "thumb" + (it.generated ? " generated" : "") + (sel.has(it.id) ? " sel" : "");
    // generated items usually have no thumbnail render → labelled placeholder box + badge.
    // ABO items keep their existing image.
    const visual = it.generated
      ? `<div class="genph" title="user-generated">◆</div>`
      : `<img src="/thumb/${it.preview || it.thumb}" loading="lazy">`;
    const badge = it.generated ? `<span class="genbadge">OURS</span>` : "";
    cell.innerHTML = badge + visual + `<div>${it.id}</div><div>${dim}</div>`;
    cell.onclick = () => {
      if (sel.has(it.id)) sel.delete(it.id); else if (sel.size < 20) sel.add(it.id);
      cell.classList.toggle("sel", sel.has(it.id));
      chosen[category] = [...sel];
      $("picker-count").textContent = sel.size;
    };
    grid.appendChild(cell);
  });
  $("picker-count").textContent = sel.size;
  $("picker").style.display = "flex";
}

function closePicker() {
  // a specific selection sets that category's count and shows it on the row
  if (pickerCat) {
    const n = (chosen[pickerCat] || []).length;
    counts[pickerCat] = n;
    const nb = $("n-" + pickerCat); if (nb) nb.textContent = n;
    updateTotal();
  }
  $("picker").style.display = "none"; pickerCat = null;
}
{ const b = $("picker-close"); if (b) b.onclick = closePicker; }
{ const b = $("picker-done"); if (b) b.onclick = closePicker; }

function total() { return Object.values(counts).reduce((a, b) => a + b, 0); }
function updateTotal() { const t = total(); $("total").textContent = t; $("total").style.color = t > 20 ? "#e05a5a" : "var(--muted)"; }
function items() {
  return Object.entries(counts).filter(([, n]) => n > 0).map(([category, count]) => {
    const ids = chosen[category];
    return (ids && ids.length) ? { category, ids } : { category, count };
  });
}

function renderChips() {
  const el = $("chips"); el.innerHTML = "";
  obstacles.forEach((o, i) => addChip(el, `column @${o.x},${o.z}`, () => { obstacles.splice(i, 1); renderChips(); }));
  doors.forEach((d, i) => addChip(el, `door @${d.x},${d.z}`, () => { doors.splice(i, 1); renderChips(); }));
}
function addChip(el, text, onClick) {
  const c = document.createElement("span"); c.className = "chip"; c.textContent = text + " ✕";
  c.onclick = onClick; el.appendChild(c);
}
$("add-col").onclick = () => { const s = +$("cols").value || 0.4; obstacles.push({ x: +$("colx").value, z: +$("colz").value, width: s, depth: s, kind: "column" }); renderChips(); };
$("add-door").onclick = () => { doors.push({ x: +$("dox").value, z: +$("doz").value, width: +$("dow").value || 0.9, depth: 0.9 }); renderChips(); };

$("gen").onclick = async () => {
  if (total() === 0) { setMsg("Pick at least one item.", true); return; }
  if (total() > 20) { setMsg("Max 20 items.", true); return; }
  setMsg("Generating layout…");
  const room = { width: +$("rw").value, depth: +$("rd").value, type: $("rtype").value, ada: $("rada").checked };
  try {
    const r = await fetch("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room, items: items(), obstacles, doors }),
    });
    const d = await r.json();
    if (!d.ok) { setMsg("Error: " + d.error, true); return; }
    setMsg(d.message, !d.feasible);
    $("meta").textContent = `· ${d.items.length} items · ${d.room.width}×${d.room.depth} m · ${d.solver}`;
    loadScene(d.glb);
    setRender(d.render);
    renderTable(d.items);
  } catch (e) { setMsg("Request failed: " + e, true); }
};

function reset() {
  // counts -> 0 (and their on-screen steppers)
  Object.keys(counts).forEach((c) => {
    counts[c] = 0;
    const n = $("n-" + c); if (n) n.textContent = "0";
  });
  Object.keys(chosen).forEach((c) => delete chosen[c]);   // clear specific-item picks
  updateTotal();
  // obstacles & doors
  obstacles.length = 0; doors.length = 0; renderChips();
  // 3D scene
  if (model) { model.destroy(); model = null; }
  // object table
  lastItems = [];
  const rows = $("rows"); if (rows) rows.innerHTML = "";
  const meta = $("meta"); if (meta) meta.textContent = "";
  // room inputs back to defaults
  if ($("rw")) $("rw").value = 8;
  if ($("rd")) $("rd").value = 6;
  if ($("rtype")) $("rtype").value = "office";
  if ($("rada")) $("rada").checked = false;
  // wipe the server-side scratch preview too — nothing is kept until you Export
  fetch("/api/reset", { method: "POST" }).catch(() => {});
  setMsg("Reset. Nothing is saved until you Export. Pick items, then Generate.");
}
{ const b = $("reset"); if (b) b.onclick = reset; }

// Server-rendered room image — a reliable visualization that needs no WebGL.
// Shown automatically when the live 3D viewer is unavailable; toggle with the 🖼 button.
function setRender(render) {
  const img = $("vfallback"), btn = $("imgview");
  if (!render) { return; }
  img.src = render + "?t=" + Date.now();
  btn.style.display = "";
  if (!gltf) showImage(true);   // no WebGL → show the rendered image
}
function showImage(on) {
  const img = $("vfallback"); if (!img) return;
  img.style.display = on ? "block" : "none";
  const btn = $("imgview"); if (btn) btn.textContent = on ? "🧊 3D" : "🖼 Image";
}
{ const b = $("imgview"); if (b) b.onclick = () => showImage($("vfallback").style.display === "none"); }

function loadScene(glb) {
  if (!gltf) return;   // no WebGL viewer — skip preview, table/IFC/CSV still work
  if (model) model.destroy();
  console.log("APPV2 loading", glb);
  model = gltf.load({ id: "room", src: glb, edges: true });
  model.on("loaded", () => {
    console.log("APPV2 loaded aabb", model.aabb);
    try { viewer.cameraFlight.jumpTo(model); } catch (e) { console.error(e); }
  });
  model.on("error", (e) => { console.error("APPV2 load error", e); setMsg("3D load error: " + e, true); });
}

function renderTable(its) {
  lastItems = its;
  const tb = $("rows"); tb.innerHTML = "";
  its.forEach((it) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td><span class="swatch" style="background:${it.material_hex}"></span>${it.name}</td>` +
      `<td class="ifc">${it.ifc_class}</td><td>${it.width_m}×${it.depth_m}×${it.height_m}</td>`;
    tb.appendChild(tr);
  });
}

function downloadBlob(name, blob) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
$("csv").onclick = () => {
  if (!lastItems.length) return;
  const cols = ["id", "name", "ifc_class", "category", "width_m", "depth_m", "height_m", "x", "z", "rotation_deg", "source", "license"];
  const lines = [cols.join(",")].concat(lastItems.map((it) => cols.map((c) => JSON.stringify(it[c] ?? "")).join(",")));
  downloadBlob("object_table.csv", new Blob([lines.join("\n")], { type: "text/csv" }));
};
$("glb").onclick = async () => {
  try { const r = await fetch("/out/scene.glb?t=" + Date.now()); if (!r.ok) throw 0; downloadBlob("scene.glb", await r.blob()); }
  catch (e) { setMsg("GLB not available — generate first.", true); }
};
$("ifc").onclick = async () => {
  try { const r = await fetch("/out/scene.ifc?t=" + Date.now()); if (!r.ok) throw 0; downloadBlob("scene.ifc", await r.blob()); }
  catch (e) { setMsg("IFC not available — generate first.", true); }
};
let camLocked = false;
function setLock(locked) {
  camLocked = locked;
  try { cc.active = !locked; } catch (e) { console.warn("camera lock unsupported:", e); }
  const b = $("lock"); if (b) b.textContent = locked ? "🔒 Locked" : "🔓 Free";
}
{ const b = $("lock"); if (b) b.onclick = () => setLock(!camLocked); }
$("fit").onclick = () => { if (model) viewer.cameraFlight.flyTo(model); };
$("walls").onclick = () => {
  if (!viewer) return;
  wallsVisible = !wallsVisible;
  Object.keys(viewer.scene.objects).forEach((id) => {
    if (id.startsWith("room-wall")) { const o = viewer.scene.objects[id]; if (o) o.visible = wallsVisible; }
  });
};

setLock(true);   // start static; guarded so it can never break init

// ============================================================================
// BUILDING POPULATION — load a real architectural IFC, choose furniture per room
// ============================================================================
const buildingSel = $("building"), buildingRooms = $("building-rooms"), populateBtn = $("populate");
let currentBuilding = "", roomPicks = {}, allCategories = [];

async function loadBuildings() {
  try {
    const bs = await (await fetch("/api/buildings")).json();
    bs.forEach((b) => { const o = document.createElement("option"); o.value = b.id; o.textContent = b.name; buildingSel.appendChild(o); });
  } catch (e) { console.warn("buildings load failed", e); }
}

buildingSel.onchange = async () => {
  currentBuilding = buildingSel.value;
  buildingRooms.innerHTML = ""; roomPicks = {};
  const sr = $("singleroom"); if (sr) sr.style.opacity = currentBuilding ? ".45" : "1";
  if (!currentBuilding) { populateBtn.style.display = "none"; return; }
  buildingRooms.innerHTML = "Loading rooms…";
  try {
    const data = await (await fetch(`/api/building/${currentBuilding}/rooms`)).json();
    allCategories = data.categories || [];
    buildingRooms.innerHTML = "";
    data.rooms.forEach((r) => { roomPicks[r.name] = [...r.suggested]; buildingRooms.appendChild(roomCard(r)); });
    populateBtn.style.display = "";
    setMsg(`${data.rooms.length} rooms loaded — edit furniture per room, then Populate.`);
  } catch (e) { buildingRooms.innerHTML = ""; setMsg("Rooms load failed: " + e, true); }
};

function roomCard(r) {
  const card = document.createElement("div"); card.className = "roomcard";
  card.innerHTML = `<div class="roomhdr"><b>${r.name}</b> <small>${r.type} · ${r.area} m²</small></div>` +
    `<div class="roomchips"></div>` +
    `<select class="roomadd"><option value="">+ add item…</option>` +
    allCategories.map((c) => `<option value="${c}">${c.replace(/_/g, " ")}</option>`).join("") + `</select>`;
  const chips = card.querySelector(".roomchips");
  const render = () => {
    chips.innerHTML = "";
    roomPicks[r.name].forEach((c, i) => {
      const chip = document.createElement("span"); chip.className = "chip"; chip.textContent = c.replace(/_/g, " ") + " ✕";
      chip.onclick = () => { roomPicks[r.name].splice(i, 1); render(); };
      chips.appendChild(chip);
    });
    if (!roomPicks[r.name].length) { const e = document.createElement("small"); e.style.color = "var(--muted)"; e.textContent = "(empty)"; chips.appendChild(e); }
  };
  render();
  card.querySelector(".roomadd").onchange = (e) => { if (e.target.value) { roomPicks[r.name].push(e.target.value); e.target.value = ""; render(); } };
  return card;
}

// --- building 3D: separate movable pieces (drag-to-reposition) ---
const bPieces = {};   // id -> {model, pos:[x,y,z], category, glb}
let bShell = null, bSelected = null, bDragging = false;

function clearBuilding() {
  if (bShell) { try { bShell.destroy(); } catch (e) {} bShell = null; }
  Object.values(bPieces).forEach((p) => { try { p.model.destroy(); } catch (e) {} });
  for (const k in bPieces) delete bPieces[k];
  bSelected = null;
}

function loadBuilding(shellUrl, pieces) {
  if (!gltf) { setMsg("3D viewer unavailable (no WebGL)", true); return; }
  clearBuilding();
  bShell = gltf.load({ id: "b-shell", src: shellUrl + "?t=" + Date.now(), edges: true });
  if (bShell) bShell.on("loaded", () => { try { viewer.cameraFlight.jumpTo(bShell); } catch (e) {} });
  pieces.forEach((pc) => {
    const model = gltf.load({ id: "bp-" + pc.id, src: pc.glb + "?t=" + Date.now(), position: pc.pos.slice() });
    if (model) { model.on("error", (e) => console.warn("piece load error", pc.id, e)); bPieces[pc.id] = { model, pos: pc.pos.slice(), category: pc.category, glb: pc.glb }; }
  });
}

function pieceIdFromPick(pr) {
  if (!pr || !pr.entity) return null;
  const mid = (pr.entity.model && pr.entity.model.id) || pr.entity.id || "";
  return String(mid).startsWith("bp-") ? String(mid).slice(3) : null;
}

if (viewer) {
  const cv = $("cv");
  cv.addEventListener("pointerdown", (e) => {
    if (!Object.keys(bPieces).length) return;
    const rect = cv.getBoundingClientRect();
    const pid = pieceIdFromPick(viewer.scene.pick({ canvasPos: [e.clientX - rect.left, e.clientY - rect.top] }));
    if (pid && bPieces[pid]) { bSelected = pid; bDragging = true; try { cc.active = false; } catch (_) {} setMsg("Dragging " + bPieces[pid].category + " — release to drop it."); }
  });
  cv.addEventListener("pointermove", (e) => {
    if (!bDragging || !bSelected) return;
    const rect = cv.getBoundingClientRect();
    const pr = viewer.scene.pick({ canvasPos: [e.clientX - rect.left, e.clientY - rect.top], pickSurface: true });
    if (pr && pr.worldPos) { const p = bPieces[bSelected]; p.pos = [pr.worldPos[0], p.pos[1], pr.worldPos[2]]; try { p.model.position = p.pos; } catch (_) {} }
  });
  const endDrag = () => {
    if (bDragging && bSelected) {
      const p = bPieces[bSelected];           // reload at final position so the move is guaranteed to show
      try { p.model.destroy(); } catch (_) {}
      p.model = gltf.load({ id: "bp-" + bSelected, src: p.glb + "?r=" + Date.now(), position: p.pos.slice() });
      setMsg("Moved " + p.category + ". Drag more, or Save layout to keep it.");
    }
    bDragging = false; try { cc.active = !camLocked; } catch (_) {}
  };
  cv.addEventListener("pointerup", endDrag);
  cv.addEventListener("pointerleave", endDrag);
}

const saveBtn = $("saveBuilding");
if (saveBtn) saveBtn.onclick = async () => {
  const positions = {}; Object.entries(bPieces).forEach(([id, p]) => { positions[id] = p.pos; });
  setMsg("Saving layout & building the export GLB…");
  try {
    const r = await fetch(`/api/building/${currentBuilding}/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ positions }) });
    const d = await r.json();
    if (!d.ok) { setMsg("Save failed: " + d.error, true); return; }
    setMsg("✓ Saved. Downloading building GLB…");
    downloadBlob("building.glb", await (await fetch(d.glb + "?t=" + Date.now())).blob());
  } catch (e) { setMsg("Save error: " + e, true); }
};

populateBtn.onclick = async () => {
  setMsg("Populating building — ergonomic solver routing around walls/beams (~30–60 s)…");
  populateBtn.disabled = true;
  try {
    const r = await fetch(`/api/building/${currentBuilding}/populate`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ picks: roomPicks }),
    });
    const d = await r.json();
    if (!d.ok) { setMsg("Populate failed: " + (d.error || "unknown"), true); return; }
    setMsg(`✓ ${d.placed} pieces · ${d.rooms} rooms · ${d.clashes} clashes — click a piece and drag to reposition.`, d.clashes > 0);
    loadBuilding(d.shell, d.pieces || []);
    if (saveBtn) saveBtn.style.display = "";
    const tb = $("rows"); if (tb) {
      tb.innerHTML = "";
      (d.schedule || []).forEach((s) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${s.room}</td><td class="ifc">${s.type}</td><td>${s.placed}/${s.items.length} placed</td>`;
        tb.appendChild(tr);
      });
    }
  } catch (e) { setMsg("Populate error: " + e, true); }
  finally { populateBtn.disabled = false; }
};

loadBuildings();
