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
    if (typeof Viewer === 'undefined') {
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

if (imageInput) {
  imageInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      selectedImage = file;

      // Show preview
      const reader = new FileReader();
      reader.onload = (e) => {
        imagePreview.innerHTML = `<img src="${e.target.result}" alt="preview">`;
        imagePreview.style.display = 'block';
      };
      reader.readAsDataURL(file);

      // Enable generate button
      generateBtn.disabled = false;
      updateStatus('Image loaded. Select model and click Generate.');
    }
  });
}

// ============================================================================
// EVENT LISTENERS - MODEL SELECTION
// ============================================================================

const modelRadios = document.querySelectorAll('input[name="model"]');
modelRadios.forEach((radio) => {
  radio.addEventListener('change', (e) => {
    selectedModel = e.target.value;
    updateStatus(`Selected model: ${selectedModel}`);
  });
});

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
    const progressContainer = document.getElementById('progressContainer');
    progressContainer.style.display = 'block';

    try {
      const glbPath = await generateModel(selectedImage, selectedModel);
      console.log('[app] Model generated:', glbPath);

      // Load into xeokit viewer
      const objectId = `obj_${Date.now()}`;
      await window.glbLoaderModule.addGLBToViewer(glbPath, objectId);

      // Add to inventory
      window.inventoryModule.addToInventory({
        name: `${selectedModel} Model`,
        modelType: selectedModel,
        glbUrl: glbPath,
        metadata: {
          generatedAt: new Date().toISOString(),
        },
      });

      updateStatus(`✓ Generated and loaded ${selectedModel} model`);
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

      await window.exporterModule.exportSceneToIFC(sceneObjects);
      // TODO: Download IFC file when Phase 6 is complete
    } catch (error) {
      console.error('[app] Export error:', error);
    } finally {
      exportIfcBtn.disabled = false;
    }
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
