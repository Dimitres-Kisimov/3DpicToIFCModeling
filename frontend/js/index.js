/**
 * Frontend application entry point - Phase 2 with xeokit integration
 */

let selectedImage = null;
let selectedModel = 'instantmesh';
let viewerInitialized = false;

// ============================================================================
// XEOKIT VIEWER INITIALIZATION
// ============================================================================

function initializeViewer() {
  if (viewerInitialized) return;

  try {
    // Wait for xeokit to load
    if (typeof window.xeokit === 'undefined' || typeof window.xeokit.Viewer === 'undefined') {
      console.warn('[app] xeokit not yet loaded, retrying...');
      setTimeout(initializeViewer, 500);
      return;
    }

    window.xeokitModule.initViewer('xeokit-container');
    viewerInitialized = true;

    // Enable object selection
    window.xeokitModule.selectObject((selectedObj) => {
      window.transformModule.setSelectedObject(selectedObj.objectId);
    });

    updateStatus('✓ Viewer ready');
  } catch (error) {
    showError('Failed to initialize viewer', error);
  }
}

// ============================================================================
// EVENT LISTENERS - IMAGE UPLOAD
// ============================================================================

const imageInput = document.getElementById('imageInput');
const imagePreview = document.getElementById('imagePreview');
const generateBtn = document.getElementById('generateBtn');

function acceptImageFile(file) {
  if (!file) return;
  if (!file.type || !file.type.startsWith('image/')) {
    showError('Please drop an image file (jpg/png/webp).');
    return;
  }
  selectedImage = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.innerHTML = `<img src="${e.target.result}" alt="preview">`;
    imagePreview.style.display = 'block';
  };
  reader.readAsDataURL(file);
  generateBtn.disabled = false;
  updateStatus(`Image loaded (${file.name || 'untitled'}). Click Generate.`);
}

if (imageInput) {
  imageInput.addEventListener('change', (e) => {
    acceptImageFile(e.target.files[0]);
  });
}

// Drag-and-drop on the upload box — avoids the OS file dialog entirely
const dropZone = document.getElementById('dropZone');
if (dropZone) {
  ['dragenter', 'dragover'].forEach(ev => {
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.add('dragging');
    });
  });
  ['dragleave', 'drop'].forEach(ev => {
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.remove('dragging');
    });
  });
  dropZone.addEventListener('drop', (e) => {
    const file = e.dataTransfer?.files?.[0];
    acceptImageFile(file);
  });
}

// Also allow paste (Ctrl+V) from clipboard
document.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      acceptImageFile(item.getAsFile());
      break;
    }
  }
});

// Sample chair button — fetches a bundled image, no file dialog needed
const useSampleBtn = document.getElementById('useSampleBtn');
if (useSampleBtn) {
  useSampleBtn.addEventListener('click', async () => {
    try {
      updateStatus('Loading sample chair photo...');
      const response = await fetch('/sample/chair.png');
      if (!response.ok) {
        showError('Sample image not found on server');
        return;
      }
      const blob = await response.blob();
      const file = new File([blob], 'chair.png', { type: blob.type || 'image/png' });
      acceptImageFile(file);
    } catch (err) {
      showError('Failed to load sample chair', err);
    }
  });
}

// ============================================================================
// PIPELINE STATUS — one source of truth for what happened on the last call
// ============================================================================
function setPipeStatus(stage, state) {
  const el = document.querySelector(`.pipe-row[data-stage="${stage}"]`);
  if (!el) return;
  el.classList.remove('active', 'success', 'skipped', 'error');
  if (state) el.classList.add(state);
}
function resetPipeStatus() {
  ['detect', 'depth', 'retrieve', 'trellis', 'fallback'].forEach(s => setPipeStatus(s, ''));
}
function applyPipelineResult(result) {
  setPipeStatus('detect', result.detection?.coco_label ? 'success' : 'error');
  setPipeStatus('depth', result.dimension_source === 'depth_anything_v2_metric' ? 'success' : 'error');

  // Cascade visualization. mesh_source values:
  //   'retrieval'  → ABO catalog won (row 3 green, rows 4+5 skipped)
  //   'trellis'    → TRELLIS in WSL won (row 3 skipped, row 4 green, row 5 skipped)
  //   'triposr'    → TripoSR won — could be because TRELLIS OOMed or TRELLIS disabled
  //   'primitive-library' → everything fell through to procedural
  const src = result.mesh_source;
  if (src === 'retrieval') {
    setPipeStatus('retrieve', 'success');
    setPipeStatus('trellis', 'skipped');
    setPipeStatus('fallback', 'skipped');
  } else if (src === 'trellis') {
    setPipeStatus('retrieve', 'skipped');
    setPipeStatus('trellis', 'success');
    setPipeStatus('fallback', 'skipped');
  } else if (src === 'triposr' || src === 'sam3d') {
    setPipeStatus('retrieve', 'skipped');
    setPipeStatus('trellis', 'skipped');   // could mark as error if we surface that
    setPipeStatus('fallback', 'success');
  } else {
    setPipeStatus('retrieve', 'skipped');
    setPipeStatus('trellis', 'skipped');
    setPipeStatus('fallback', 'skipped');
  }
}

// ============================================================================
// EVENT LISTENERS - GENERATE BUTTON
// ============================================================================

if (generateBtn) {
  generateBtn.addEventListener('click', async () => {
    if (!selectedImage) {
      showError('Please select an image first');
      return;
    }

    if (!viewerInitialized) {
      showError('Viewer not initialized');
      return;
    }

    generateBtn.disabled = true;
    resetPipeStatus();
    const engine = (document.getElementById('engineSelect')?.value) || 'detect';
    const activeStages = engine === 'triposr' ? ['detect', 'depth', 'fallback']
                                              : ['detect', 'depth', 'retrieve'];
    activeStages.forEach(s => setPipeStatus(s, 'active'));
    const progressContainer = document.getElementById('progressContainer');
    progressContainer.style.display = 'block';

    try {
      const result = await generateModel(selectedImage, engine);
      console.log('[app] Pipeline result:', result);
      applyPipelineResult(result);
      const glbPath = result.glb;

      // Load into xeokit viewer
      const objectId = `obj_${Date.now()}`;
      await window.glbLoaderModule.addGLBToViewer(glbPath, objectId);

      // Store objectId → glbPath so export can find the file
      window._objectGlbMap = window._objectGlbMap || {};
      window._objectGlbMap[objectId] = glbPath;

      // Store full per-object detection metadata so IFC export can use it
      window._objectMetadataMap = window._objectMetadataMap || {};
      window._objectMetadataMap[objectId] = {
        name: result.category ? result.category.replace(/_/g, ' ') : 'Object',
        ifcClass: result.ifcClass || null,
        category: result.category || null,
        dimensions: result.dimensions_m || null,
        confidence: result.detection?.confidence ?? null,
        cocoLabel: result.detection?.coco_label || null,
        extraMeta: result.extra_meta || result.extraMeta || null,
      };

      // Add to inventory with rich metadata from the pipeline
      const category = result.category || 'unknown';
      const ifcClass = result.ifcClass || 'IfcFurnishingElement';
      const conf = result.detection?.confidence ?? 0;
      const dims = result.dimensions_m || {};
      const displayName = `${category.replace(/_/g, ' ')} (${(conf * 100).toFixed(0)}%)`;

      window.inventoryModule.addToInventory({
        id: objectId,
        name: displayName,
        modelType: 'detect-and-place',
        category,
        ifcClass,
        confidence: conf,
        dimensions: dims,
        cocoLabel: result.detection?.coco_label,
        glbUrl: glbPath,
        metadata: {
          generatedAt: new Date().toISOString(),
          faces: result.metadata?.faces,
          latencyMs: result.metadata?.latencyMs,
          method: result.metadata?.method,
        },
      });

      // Enable export now that we have at least one object
      const exportBtn = document.getElementById('exportIfcBtn');
      if (exportBtn) exportBtn.disabled = false;

      updateStatus(`✓ Detected ${category} → ${ifcClass} (${dims.height || '?'}m × ${dims.width || '?'}m × ${dims.depth || '?'}m)`);
    } catch (error) {
      console.error('[app] Generation error:', error);
      showError('Failed to generate model', error);
    } finally {
      generateBtn.disabled = false;
      progressContainer.style.display = 'none';
    }
  });
}

// ============================================================================
// EVENT LISTENERS - EXPORT
// ============================================================================

const exportIfcBtn = document.getElementById('exportIfcBtn');

if (exportIfcBtn) {
  exportIfcBtn.addEventListener('click', async () => {
    try {
      exportIfcBtn.disabled = true;
      const sceneObjects = window.exporterModule.prepareSceneForExport();

      if (sceneObjects.length === 0) {
        showError('No objects in scene to export');
        return;
      }

      const ifcPath = await window.exporterModule.exportSceneToIFC(sceneObjects);
      // Trigger browser download of the exported IFC file
      if (ifcPath) {
        // Handle BOTH forward and back slashes (Windows server paths use '\') and use the
        // server URL directly when it's already a /outputs/.. path.
        const filename = ifcPath.split(/[\\/]/).pop() || 'export.ifc';
        const href = ifcPath.startsWith('/') ? ifcPath : `/outputs/${filename}`;
        const link = document.createElement('a');
        link.href = href;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showSuccess(`IFC downloaded: ${filename}`);
      } else {
        showError('Export returned no file — check the server log');
      }
    } catch (error) {
      console.error('[app] Export error:', error);
      showError('Export failed: ' + (error && error.message ? error.message : String(error)), error);
    } finally {
      exportIfcBtn.disabled = false;
    }
  });
}

// ============================================================================
// CLEAR VIEW (keeps inventory + export data) + EXPORT MODES (table / each)
// ============================================================================

// Clear ONLY the 3D scene — inventory and the export map (_objectGlbMap) are kept, so you can
// take another photo with a clean viewer and still export everything together at the end.
const clearViewBtn = document.getElementById('clearViewBtn');
if (clearViewBtn) {
  clearViewBtn.addEventListener('click', () => {
    try { window.xeokitModule.clearScene(); } catch (e) { console.warn(e); }
    const n = ((window.inventoryModule && window.inventoryModule.getInventory()) || []).length;
    showSuccess(`3D view cleared — inventory kept (${n} item${n === 1 ? '' : 's'})`);
  });
}

// Export the inventory as a spreadsheet TABLE (schedule CSV) — the object list with BIM metadata.
const exportTableBtn = document.getElementById('exportTableBtn');
if (exportTableBtn) {
  exportTableBtn.addEventListener('click', () => {
    const items = (window.inventoryModule && window.inventoryModule.getInventory()) || [];
    if (!items.length) { showError('Inventory is empty — generate something first'); return; }
    const cols = ['id', 'name', 'category', 'ifc_class', 'width_m', 'depth_m', 'height_m',
                  'confidence', 'coco_label', 'source', 'license', 'glb'];
    const q = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
    const rows = items.map((it) => {
      const d = it.dimensions || {}; const em = (it.metadata && it.metadata.extraMeta) || it.metadata || {};
      return [it.id, it.name, it.category, it.ifcClass, d.width, d.depth, d.height,
              it.confidence, it.cocoLabel, em.source, em.license, it.glbUrl || it.glbPath].map(q).join(',');
    });
    const csv = [cols.join(','), ...rows].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a'); a.href = url; a.download = 'inventory_schedule.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
    showSuccess(`Table exported: ${items.length} items → inventory_schedule.csv`);
  });
}

// Export EACH inventory item as its own IFC file (one download per item).
const exportEachBtn = document.getElementById('exportEachBtn');
if (exportEachBtn) {
  exportEachBtn.addEventListener('click', async () => {
    const map = window._objectGlbMap || {}; const meta = window._objectMetadataMap || {};
    const ids = Object.keys(map).filter((id) => map[id]);
    if (!ids.length) { showError('Nothing to export — generate something first'); return; }
    exportEachBtn.disabled = true;
    showSuccess(`Exporting ${ids.length} items separately…`);
    let ok = 0;
    for (const id of ids) {
      const m = meta[id] || {};
      const obj = { id, glbPath: map[id], glbUrl: map[id], name: m.name || 'Object',
                    ifcClass: m.ifcClass || null, category: m.category || null,
                    dimensions: m.dimensions || null, extraMeta: m.extraMeta || null,
                    position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
      try {
        const ifcPath = await window.exporterModule.exportSceneToIFC([obj]);
        if (ifcPath) {
          const fn = ifcPath.split(/[\\/]/).pop();
          const a = document.createElement('a');
          a.href = ifcPath.startsWith('/') ? ifcPath : `/outputs/${fn}`;
          a.download = `${(m.category || 'object')}_${fn}`;
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          ok++; await new Promise((r) => setTimeout(r, 400));  // small gap so the browser allows each download
        }
      } catch (e) { console.error('[app] export-each failed for', id, e); }
    }
    exportEachBtn.disabled = false;
    showSuccess(`Exported ${ok}/${ids.length} items as separate IFC files`);
  });
}

// ============================================================================
// EVENT LISTENERS - TRANSFORM CONTROLS
// ============================================================================

const snapToGroundBtn = document.getElementById('snapToGroundBtn');
const resetTransformBtn = document.getElementById('resetTransformBtn');

if (snapToGroundBtn) {
  snapToGroundBtn.addEventListener('click', () => {
    const objId = window.transformModule.getSelectedObject();
    if (objId) {
      window.transformModule.snapToGround(objId);
      window.transformModule.updateTransformUI();
    }
  });
}

if (resetTransformBtn) {
  resetTransformBtn.addEventListener('click', () => {
    const objId = window.transformModule.getSelectedObject();
    if (objId) {
      window.transformModule.resetTransform(objId);
      window.transformModule.updateTransformUI();
    }
  });
}

// Listen for transform input changes
const transformInputs = document.querySelectorAll('.transform-input');
transformInputs.forEach((input) => {
  input.addEventListener('change', () => {
    window.transformModule.applyTransformFromUI();
  });
});

// ============================================================================
// EVENT LISTENERS - DEBUG
// ============================================================================

const healthCheckBtn = document.getElementById('healthCheckBtn');
const healthInfo = document.getElementById('healthInfo');

if (healthCheckBtn) {
  healthCheckBtn.addEventListener('click', async () => {
    healthInfo.innerHTML = '<pre>Checking...</pre>';

    try {
      const result = await fetchDebugHealth();
      healthInfo.innerHTML = `<pre>${JSON.stringify(result, null, 2)}</pre>`;
    } catch (error) {
      healthInfo.innerHTML = `<pre>Error: ${error.message}</pre>`;
    }
  });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  console.log('[app] Frontend initialized');

  // Initialize viewer when xeokit loads
  setTimeout(initializeViewer, 1000);

  updateStatus('Initializing...');
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Delete') {
    const objId = window.transformModule.getSelectedObject();
    if (objId) {
      window.xeokitModule.removeObject(objId);
      updateStatus('✓ Object deleted');
    }
  }

  // Arrow keys for movement
  const objId = window.transformModule.getSelectedObject();
  if (!objId) return;

  const step = 0.1;
  switch (e.key) {
    case 'ArrowUp':
      e.preventDefault();
      window.transformModule.moveObject(objId, [0, step, 0]);
      break;
    case 'ArrowDown':
      e.preventDefault();
      window.transformModule.moveObject(objId, [0, -step, 0]);
      break;
    case 'ArrowLeft':
      e.preventDefault();
      window.transformModule.moveObject(objId, [-step, 0, 0]);
      break;
    case 'ArrowRight':
      e.preventDefault();
      window.transformModule.moveObject(objId, [step, 0, 0]);
      break;
  }
});
