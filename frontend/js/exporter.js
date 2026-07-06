/**
 * Exporter Module - Phase 6 (preview for Phase 2)
 * Handles IFC and other format exports
 */

/**
 * Prepare scene data for export
 * @returns {Array} - Array of scene objects
 */
function prepareSceneForExport() {
  const glbMap = window._objectGlbMap || {};
  const meta = window._objectMetadataMap || {};

  // Live transforms from the viewer, indexed by id (best-effort: the viewer's entity ids may
  // differ from our object ids, so we match when we can and default otherwise). Guarded so a
  // viewer hiccup can never break export.
  const transforms = {};
  try {
    const sceneData = (window.xeokitModule && window.xeokitModule.exportSceneData)
      ? (window.xeokitModule.exportSceneData() || []) : [];
    sceneData.forEach(o => { if (o && o.id) transforms[o.id] = o; });
  } catch (e) {
    console.warn('[exporter] exportSceneData failed; using default transforms', e);
  }

  // Build the export list from what we ACTUALLY generated + registered — robust to viewer id mismatch.
  const objects = Object.keys(glbMap).filter(id => glbMap[id]).map(id => {
    const m = meta[id] || {};
    const t = transforms[id] || {};
    return {
      id,
      glbPath: glbMap[id],
      glbUrl: glbMap[id],
      position: t.position || [0, 0, 0],
      rotation: t.rotation || [0, 0, 0],
      scale: t.scale || [1, 1, 1],
      name: m.name || 'Object',
      ifcClass: m.ifcClass || null,
      category: m.category || null,
      dimensions: m.dimensions || null,
      extraMeta: m.extraMeta || null,
    };
  });

  console.log('[exporter] Prepared scene:', objects.length, 'objects for export');
  return objects;
}

/**
 * Export scene to IFC format
 * @param {Array} sceneObjects - Objects to export
 * @returns {Promise<string>} - IFC file path or blob
 */
async function exportSceneToIFC(sceneObjects) {
  try {
    updateStatus('Exporting to IFC...');

    const response = await fetch(`${API_BASE}/export/ifc`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ objects: sceneObjects }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error?.message || 'Export failed');
    }

    const opt = data.optimized;
    if (opt && opt.ok) {
      showSuccess(`✓ IFC exported + optimized — ${opt.faces_reduction_pct}% fewer faces, ${opt.size_reduction_pct}% smaller file`);
    } else {
      showSuccess('IFC exported successfully');
    }
    console.log('[exporter] IFC exported:', data.ifcUrl || data.ifcPath, opt || '');
    return data.ifcUrl || data.ifcPath;   // prefer the server URL (/outputs/..) over the raw OS path
  } catch (error) {
    showError('IFC export failed', error);
    throw error;
  }
}

/**
 * Export scene to JSON
 * @returns {string} - JSON scene data
 */
function exportSceneToJSON() {
  const sceneData = prepareSceneForExport();
  return JSON.stringify(sceneData, null, 2);
}

/**
 * Download JSON scene
 */
function downloadSceneJSON() {
  const json = exportSceneToJSON();
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `scene_${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  console.log('[exporter] Downloaded scene JSON');
}

// Export functions
window.exporterModule = {
  prepareSceneForExport,
  exportSceneToIFC,
  exportSceneToJSON,
  downloadSceneJSON,
};
