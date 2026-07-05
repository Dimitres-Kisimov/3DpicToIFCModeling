/**
 * xeokit Viewer Module - Phase 2
 * Initializes and manages the 3D xeokit viewer
 */

let viewer = null;
let canvas = null;
let gltfLoader = null;

/**
 * Initialize xeokit viewer
 * @param {string} containerId - ID of the container element
 * @returns {object} - Viewer instance
 */
function initViewer(containerId) {
  if (viewer) {
    console.warn('[xeokitViewer] Viewer already initialized');
    return viewer;
  }

  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`[xeokitViewer] Container not found: ${containerId}`);
    throw new Error(`Container not found: ${containerId}`);
  }

  try {
    // Check if xeokit is available before touching the DOM
    if (typeof window.xeokit === 'undefined' || typeof window.xeokit.Viewer === 'undefined') {
      throw new Error('xeokit SDK not loaded. Check CDN connection.');
    }

    // Create canvas element with explicit pixel dimensions so xeokit can initialize WebGL
    canvas = document.createElement('canvas');
    canvas.id = 'xeokit-canvas';
    // Absolute + block so the canvas is pulled OUT of normal flow. An inline
    // canvas at height:100% inside a %-height chain feeds its own baseline gap
    // back into layout every frame — the page slowly grows and the model drifts
    // downward. Locking it to the container's box kills that loop.
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    container.innerHTML = ''; // Clear placeholder
    container.appendChild(canvas);
    canvas.width = container.clientWidth || 800;
    canvas.height = container.clientHeight || 600;

    // Initialize viewer using xeokit.Viewer
    viewer = new window.xeokit.Viewer({
      canvasId: 'xeokit-canvas',
      transparent: true,
    });

    // Initialize GLTFLoaderPlugin for loading GLB/GLTF files
    gltfLoader = new window.xeokit.GLTFLoaderPlugin(viewer);

    // Setup camera for good initial view
    viewer.camera.eye = [0, 0, 3];
    viewer.camera.look = [0, 0, 0];
    viewer.camera.up = [0, 1, 0];
    viewer.cameraFlight.fitFOV = 55;   // zoom models in to fill the view
    viewer.cameraFlight.duration = 0.5;

    // Camera controls: orbit + zoom-toward-cursor (fixes "can't zoom properly")
    try {
      const cc = viewer.cameraControl;
      cc.navMode = 'orbit';
      cc.followPointer = true;
      cc.mouseWheelDollyRate = 20;
    } catch (e) { console.warn('[xeokitViewer] cameraControl setup', e); }

    updateStatus('✓ xeokit viewer initialized');
    console.log('[xeokitViewer] Viewer initialized successfully');

    return viewer;
  } catch (error) {
    showError(`Failed to initialize xeokit viewer: ${error.message}`, error);
    throw error;
  }
}

/**
 * Load GLB file into viewer
 * @param {string} glbUrl - URL to GLB file
 * @param {string} objectId - Unique object ID
 * @param {object} options - Additional options
 * @returns {Promise<object>} - Loaded model entity
 */
async function loadGLBModel(glbUrl, objectId, options = {}) {
  if (!viewer || !gltfLoader) {
    showError('Viewer not initialized');
    return null;
  }

  return new Promise((resolve, reject) => {
    updateStatus(`Loading 3D model: ${objectId}`);

    const model = gltfLoader.load({
      id: objectId,
      src: glbUrl,
      edges: false,
    });

    model.on('loaded', () => {
      // Pipeline emits height along X. rz=90 stands it upright; because it's stood up by the Z
      // rotation, the horizontal SPIN (left/right facing) is controlled by the X-euler, not Y.
      // Default spin 180° to face the camera; the Rotate button steps this X-euler by 90°.
      model._spin = 180;
      try { model.rotation = [model._spin, 0, 90]; } catch (e) { console.warn('rotate failed', e); }
      window._lastModel = model;
      try { viewer.cameraFlight.flyTo(model); }
      catch (e) { try { viewer.cameraFlight.jumpTo(model); } catch (_) {} }
      updateStatus(`✓ Model loaded: ${objectId}`);
      resolve(model);
    });

    model.on('error', (errMsg) => {
      showError(`Failed to load GLB model: ${objectId}`, errMsg);
      reject(new Error(errMsg));
    });
  });
}

/**
 * Select an object in the viewer
 * @param {function} callback - Callback when object is selected
 */
function selectObject(callback) {
  if (!viewer) {
    console.warn('[xeokitViewer] Viewer not initialized');
    return;
  }

  // Listen for canvas clicks
  canvas.addEventListener('click', (event) => {
    const pickResult = viewer.scene.pick({
      canvasPos: [event.clientX - canvas.getBoundingClientRect().left, event.clientY - canvas.getBoundingClientRect().top],
    });

    if (pickResult) {
      console.log('[xeokitViewer] Object selected:', pickResult.entity.id);
      
      // Highlight selected entity
      if (pickResult.entity) {
        pickResult.entity.highlighted = true;
        
        if (callback) {
          callback({
            objectId: pickResult.entity.id,
            entity: pickResult.entity,
            primitiveId: pickResult.primitiveIndex,
          });
        }
      }
    } else {
      // Deselect all
      const entities = viewer.scene.entities;
      for (const entity of Object.values(entities)) {
        entity.highlighted = false;
      }
    }
  });

  updateStatus('✓ Object selection enabled - click to select');
}

/**
 * Update object transform (position, rotation, scale)
 * @param {string} objectId - Object ID
 * @param {Array} position - [x, y, z]
 * @param {Array} rotation - [x, y, z] in degrees
 * @param {Array} scale - [x, y, z]
 */
function updateObjectTransform(objectId, position = null, rotation = null, scale = null) {
  if (!viewer) {
    console.warn('[xeokitViewer] Viewer not initialized');
    return;
  }

  const entity = viewer.scene.entities[objectId];
  if (!entity) {
    console.warn(`[xeokitViewer] Object not found: ${objectId}`);
    return;
  }

  if (position) {
    entity.position = position;
  }

  if (rotation) {
    // Convert degrees to radians
    const rotRad = [
      (rotation[0] * Math.PI) / 180,
      (rotation[1] * Math.PI) / 180,
      (rotation[2] * Math.PI) / 180,
    ];
    // This is a simplified rotation - real implementation would need quaternions
    entity.rotation = rotRad;
  }

  if (scale) {
    entity.scale = scale;
  }

  console.log(`[xeokitViewer] Updated transform for ${objectId}`);
}

/**
 * Get all entities in scene
 * @returns {Array} - Array of entity IDs
 */
function getSceneObjects() {
  if (!viewer) return [];
  return Object.keys(viewer.scene.entities);
}

/**
 * Remove object from viewer
 * @param {string} objectId - Object ID to remove
 */
function removeObject(objectId) {
  if (!viewer) return;

  const entity = viewer.scene.entities[objectId];
  if (entity) {
    entity.destroy();
    console.log(`[xeokitViewer] Removed object: ${objectId}`);
  }
}

/**
 * Clear all objects from viewer
 */
function clearScene() {
  if (!viewer) return;

  const entities = Object.keys(viewer.scene.entities);
  entities.forEach((id) => {
    removeObject(id);
  });

  console.log('[xeokitViewer] Scene cleared');
  updateStatus('Scene cleared');
}

/**
 * Export scene for IFC conversion
 * @returns {Array} - Array of objects with geometry and transforms
 */
function exportSceneData() {
  if (!viewer) return [];

  const sceneData = [];
  const entities = viewer.scene.entities;

  for (const [id, entity] of Object.entries(entities)) {
    sceneData.push({
      id: id,
      position: entity.position || [0, 0, 0],
      rotation: entity.rotation || [0, 0, 0],
      scale: entity.scale || [1, 1, 1],
      // Entity geometry would need to be extracted separately
    });
  }

  return sceneData;
}

/** Re-frame the camera to fit everything in view. */
function fitView() {
  if (!viewer) return;
  try { viewer.cameraFlight.flyTo(viewer.scene); }
  catch (e) { try { viewer.cameraFlight.jumpTo(viewer.scene); } catch (_) {} }
}

/** Spin the most-recently-loaded model about its vertical (X-euler, because rz=90 stands it up). */
function rotateLastModel(deltaDeg = 90) {
  const m = window._lastModel;
  if (!m) return;
  m._spin = ((((m._spin || 0) + deltaDeg) % 360) + 360) % 360;
  try { m.rotation = [m._spin, 0, 90]; } catch (e) { console.warn('[xeokitViewer] rotate', e); }
  fitView();
}

// Export functions
window.xeokitModule = {
  initViewer,
  loadGLBModel,
  selectObject,
  updateObjectTransform,
  getSceneObjects,
  removeObject,
  clearScene,
  exportSceneData,
  fitView,
  rotateLastModel,
  getViewer: () => viewer,
  getLoader: () => gltfLoader,
};
