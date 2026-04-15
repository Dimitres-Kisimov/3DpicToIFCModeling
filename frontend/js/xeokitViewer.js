/**
 * xeokit Viewer Module - Phase 2
 * Initializes and manages the 3D xeokit viewer
 */

let viewer = null;
let canvas = null;

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
    // Create canvas element
    canvas = document.createElement('canvas');
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    container.innerHTML = ''; // Clear placeholder
    container.appendChild(canvas);

    // Initialize viewer
    viewer = new Viewer({
      canvas: canvas,
      transparent: true,
    });

    // Setup camera for good initial view
    viewer.camera.eye = [0, 0, 3];
    viewer.camera.look = [0, 0, 0];
    viewer.camera.up = [0, 1, 0];

    updateStatus('✓ xeokit viewer initialized');
    console.log('[xeokitViewer] Viewer initialized successfully');

    return viewer;
  } catch (error) {
    showError('Failed to initialize xeokit viewer', error);
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
  if (!viewer) {
    showError('Viewer not initialized');
    return null;
  }

  try {
    updateStatus(`Loading 3D model: ${objectId}`);

    const model = await viewer.scene.importModel(
      {
        id: objectId,
        src: glbUrl,
        metaModelId: 'GLBModel',
      },
      () => {
        console.log(`[xeokitViewer] Model loaded: ${objectId}`);
      }
    );

    // Auto-fit model into view
    viewer.cameraFlight.flyTo(
      {
        aabb: viewer.scene.getAABB(),
        duration: 1.0,
      },
      () => {
        console.log('[xeokitViewer] Camera fitted to model');
      }
    );

    updateStatus(`✓ Model loaded: ${objectId}`);
    return model;
  } catch (error) {
    showError(`Failed to load GLB model: ${objectId}`, error);
    throw error;
  }
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
  getViewer: () => viewer,
};
