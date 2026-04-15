/**
 * GLB Loader Module - Phase 2
 * Handles loading and processing GLB files
 */

/**
 * Load GLB from file or URL
 * @param {string|Blob} source - File URL or Blob
 * @returns {Promise<Blob>} - GLB blob data
 */
async function loadGLBFile(source) {
  try {
    updateStatus('Loading GLB file...');

    let glbData;

    if (typeof source === 'string') {
      // Load from URL
      const response = await fetch(source);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      glbData = await response.blob();
    } else if (source instanceof Blob) {
      // Already a blob
      glbData = source;
    } else {
      throw new Error('Invalid GLB source');
    }

    console.log('[glbLoader] GLB loaded:', glbData.size, 'bytes');
    return glbData;
  } catch (error) {
    showError('Failed to load GLB file', error);
    throw error;
  }
}

/**
 * Add GLB to xeokit viewer
 * @param {string} glbUrl - URL to GLB file
 * @param {string} objectId - Unique object ID
 * @returns {Promise<object>} - Loaded entity
 */
async function addGLBToViewer(glbUrl, objectId) {
  try {
    const viewer = window.xeokitModule.getViewer();
    if (!viewer) {
      throw new Error('Viewer not initialized');
    }

    // Load GLB through xeokit
    const entity = await window.xeokitModule.loadGLBModel(glbUrl, objectId);
    console.log('[glbLoader] Added to viewer:', objectId);
    return entity;
  } catch (error) {
    showError('Failed to add GLB to viewer', error);
    throw error;
  }
}

/**
 * Create downloadable GLB blob
 * @param {ArrayBuffer} glbBuffer - GLB binary data
 * @returns {Blob} - GLB blob
 */
function createGLBBlob(glbBuffer) {
  return new Blob([glbBuffer], { type: 'model/gltf-binary' });
}

/**
 * Download GLB file to user's computer
 * @param {Blob} glbBlob - GLB blob data
 * @param {string} filename - Output filename
 */
function downloadGLB(glbBlob, filename = 'model.glb') {
  const url = URL.createObjectURL(glbBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  console.log('[glbLoader] Downloaded:', filename);
}

/**
 * Validate GLB file format
 * @param {ArrayBuffer} buffer - File data
 * @returns {boolean} - Is valid GLB
 */
function isValidGLB(buffer) {
  // GLB files start with magic number 0x46546C67 ("glTF" in ASCII)
  const view = new Uint8Array(buffer);
  if (view.length < 12) return false;

  const magic = (view[3] << 24) | (view[2] << 16) | (view[1] << 8) | view[0];
  return magic === 0x46546c67; // "glTF" in little-endian
}

/**
 * Get GLB file info/metadata
 * @param {ArrayBuffer} buffer - GLB data
 * @returns {object} - GLB info
 */
function getGLBInfo(buffer) {
  const view = new DataView(buffer);

  return {
    magic: '0x' + view.getUint32(0, true).toString(16),
    version: view.getUint32(4, true),
    length: view.getUint32(8, true),
    isValid: isValidGLB(buffer),
  };
}

// Export functions
window.glbLoaderModule = {
  loadGLBFile,
  addGLBToViewer,
  createGLBBlob,
  downloadGLB,
  isValidGLB,
  getGLBInfo,
};
