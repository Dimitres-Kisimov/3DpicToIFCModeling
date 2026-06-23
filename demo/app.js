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
  setTimeout(() => setMsg("3D preview off (no WebGL — close other tabs / enable hardware acceleration, then refresh). You can still pick items, Generate, and Export IFC/CSV.", true), 0);
}
let model = null, wallsVisible = true, lastItems = [];
const counts = {};
const obstacles = [], doors = [];

loadCatalog();   // load items FIRST, before any handler wiring, so the list always populates

function setMsg(t, bad) { const m = $("msg"); m.textContent = t; m.className = bad ? "bad" : ""; }

async function loadCatalog() {
  const cats = await (await fetch("/api/catalog")).json();
  const el = $("catalog");
  cats.forEach((c) => {
    counts[c.category] = 0;
    const row = document.createElement("div");
    row.className = "catrow";
    row.innerHTML =
      `<span>${c.label} <small>${c.abo ? "· ABO" : "· prim"}</small></span>` +
      `<span class="step"><button data-c="${c.category}" data-d="-1">−</button>` +
      `<b id="n-${c.category}">0</b><button data-c="${c.category}" data-d="1">+</button></span>`;
    el.appendChild(row);
  });
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-c]"); if (!b) return;
    const c = b.dataset.c;
    counts[c] = Math.max(0, counts[c] + (+b.dataset.d));
    $("n-" + c).textContent = counts[c];
    updateTotal();
  });
}

function total() { return Object.values(counts).reduce((a, b) => a + b, 0); }
function updateTotal() { const t = total(); $("total").textContent = t; $("total").style.color = t > 20 ? "#e05a5a" : "var(--muted)"; }
function items() { return Object.entries(counts).filter(([, n]) => n > 0).map(([category, count]) => ({ category, count })); }

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
    renderTable(d.items);
  } catch (e) { setMsg("Request failed: " + e, true); }
};

function reset() {
  // counts -> 0 (and their on-screen steppers)
  Object.keys(counts).forEach((c) => {
    counts[c] = 0;
    const n = $("n-" + c); if (n) n.textContent = "0";
  });
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
