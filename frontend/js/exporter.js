/**
 * Exporter Module - Phase 6 (preview for Phase 2)
 * Handles IFC and other format exports
 */

/**
 * Prepare scene data for export
 * @returns {Array} - Array of scene objects
 */
function prepareSceneForExport() {
  const sceneData = window.xeokitModule.exportSceneData();
  console.log('[exporter] Prepared scene data:', sceneData.length, 'objects');
  return sceneData;
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

    showSuccess('IFC exported successfully');
    console.log('[exporter] IFC exported:', data.ifcPath);
    return data.ifcPath;
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
