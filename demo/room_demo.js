import { Viewer, GLTFLoaderPlugin } from "../node_modules/@xeokit/xeokit-sdk/dist/xeokit-sdk.min.es.js";

const statusEl = document.getElementById("status");
const setStatus = (s) => { statusEl.textContent = s; };

const viewer = new Viewer({ canvasId: "viewer-canvas", transparent: false });
viewer.camera.eye = [9, 7, 9];
viewer.camera.look = [3, 0.5, 2];
viewer.camera.up = [0, 1, 0];

// Stable controls: no auto-drift, pointer-independent, clean mouse-wheel zoom.
const cc = viewer.cameraControl;
cc.navMode = "orbit";
cc.followPointer = false;
cc.rotationInertia = 0;
cc.dollyInertia = 0;
cc.panInertia = 0;
cc.mouseWheelDollyRate = 30;

const gltf = new GLTFLoaderPlugin(viewer);
let sceneModel = null;
let wallsVisible = true;

function loadScene() {
  if (sceneModel) sceneModel.destroy();
  setStatus("loading model…");
  sceneModel = gltf.load({
    id: "room",
    src: "out/scene.glb",
    metaModelSrc: "out/metamodel.json",
    edges: true,
  });
  sceneModel.on("loaded", () => { viewer.cameraFlight.jumpTo(sceneModel); setStatus("ready"); });
  sceneModel.on("error", (e) => setStatus("load error: " + e));
}

function highlight(id, on) {
  try { viewer.scene.setObjectsHighlighted([id], on); } catch (e) { /* id may not be an object */ }
}

function selectRow(id, tr) {
  document.querySelectorAll("tbody tr").forEach((r) => {
    r.classList.remove("sel");
    highlight(r.dataset.id, false);
  });
  tr.classList.add("sel");
  highlight(id, true);
  const obj = viewer.scene.objects[id];
  if (obj) { try { viewer.cameraFlight.flyTo(obj); } catch (e) {} }
}

async function loadTable() {
  const data = await (await fetch("out/schedule.json")).json();
  window._schedule = data;
  document.getElementById("table-meta").textContent =
    `${data.items.length} objects · room ${data.room.width}×${data.room.depth} m · solver: ${data.solver}`;
  const tbody = document.getElementById("rows");
  tbody.innerHTML = "";
  for (const it of data.items) {
    const tr = document.createElement("tr");
    tr.dataset.id = it.id;
    tr.innerHTML =
      `<td><span class="swatch" style="background:${it.material_hex}"></span>${it.name}</td>` +
      `<td class="ifc">${it.ifc_class}</td>` +
      `<td>${it.width_m}×${it.depth_m}×${it.height_m}</td>` +
      `<td class="lic">${it.source || "—"}<br>${it.license || ""}</td>`;
    tr.addEventListener("click", () => selectRow(it.id, tr));
    tr.addEventListener("mouseenter", () => highlight(it.id, true));
    tr.addEventListener("mouseleave", () => { if (!tr.classList.contains("sel")) highlight(it.id, false); });
    tbody.appendChild(tr);
  }
}

function downloadBlob(name, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportCSV() {
  const d = window._schedule;
  if (!d) return;
  const cols = ["id", "name", "ifc_class", "category", "width_m", "depth_m", "height_m",
                "qty", "material_hex", "x", "z", "rotation_deg", "source", "license"];
  const lines = [cols.join(",")].concat(
    d.items.map((it) => cols.map((c) => JSON.stringify(it[c] ?? "")).join(",")));
  downloadBlob("object_table.csv", new Blob([lines.join("\n")], { type: "text/csv" }));
}

async function exportIFC() {
  try {
    const r = await fetch("out/scene.ifc");
    if (!r.ok) throw new Error("missing");
    downloadBlob("scene.ifc", await r.blob());
  } catch (e) {
    setStatus("scene.ifc not built yet — run build_room_ifc.py");
  }
}

document.getElementById("btn-fit").onclick = () => { if (sceneModel) viewer.cameraFlight.flyTo(sceneModel); };
document.getElementById("btn-walls").onclick = () => {
  wallsVisible = !wallsVisible;
  ["room-wall-back", "room-wall-left"].forEach((id) => {
    const o = viewer.scene.objects[id];
    if (o) o.visible = wallsVisible;
  });
};
document.getElementById("btn-shot").onclick = () => {
  try {
    const dataURL = viewer.getSnapshot({ width: 1600, height: 1000, format: "png" });
    const a = document.createElement("a");
    a.href = dataURL; a.download = "room_render.png"; a.click();
  } catch (e) { setStatus("snapshot failed: " + e); }
};
document.getElementById("btn-csv").onclick = exportCSV;
document.getElementById("btn-ifc").onclick = exportIFC;
document.getElementById("btn-layout").onclick = () =>
  setStatus("Re-layout re-runs build_room_scene.py (wired via run_demo.ps1).");

loadScene();
loadTable();
