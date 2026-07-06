/**
 * API client for 3D-to-IFC application
 */

const API_BASE = 'http://localhost:3000/api';

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function updateStatus(message) {
  const statusEl = document.getElementById('statusMessage');
  if (statusEl) {
    statusEl.textContent = message;
    console.log(`[STATUS] ${message}`);
  }
}

function showError(message, error = null) {
  updateStatus(`❌ ${message}`);
  console.error(message, error);
  alert(`Error: ${message}`);
}

function showSuccess(message) {
  updateStatus(`✓ ${message}`);
  console.log(`[SUCCESS] ${message}`);
}

// ============================================================================
// API CALLS
// ============================================================================

async function fetchHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Health check failed', error);
    throw error;
  }
}

async function fetchDebugHealth() {
  try {
    const response = await fetch(`${API_BASE}/debug/health`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Debug health check failed', error);
    throw error;
  }
}

async function fetchAvailableModels() {
  try {
    const response = await fetch(`${API_BASE}/models/available`);
    const data = await response.json();
    return data.models || [];
  } catch (error) {
    console.error('Failed to fetch available models', error);
    throw error;
  }
}

async function generateModel(imageBlob, modelName, opts = {}) {
  try {
    const formData = new FormData();
    formData.append('image', imageBlob, 'uploaded_image');
    formData.append('model', modelName);
    if (opts.graftBase) formData.append('graftBase', '1');   // office-chair: graft a clean 5-star base

    updateStatus(`Detecting object and generating 3D model...`);

    const response = await fetch(`${API_BASE}/generate`, {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error?.message || 'Generation failed');
    }

    const detected = data.detection?.coco_label || 'unknown';
    const conf = data.detection?.confidence ?? 0;
    showSuccess(`Detected ${detected} (${(conf * 100).toFixed(1)}%) → ${data.ifcClass}`);
    return data;  // return full result object: glb, glbPath, detection, category, ifcClass, dimensions_m, metadata
  } catch (error) {
    showError('Model generation failed', error);
    throw error;
  }
}

async function exportToIFC(sceneObjects) {
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
    return data.ifcPath;
  } catch (error) {
    showError('IFC export failed', error);
    throw error;
  }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  updateStatus('Initializing...');

  // Test API connectivity
  fetchHealth()
    .then(() => {
      showSuccess('API connected');
    })
    .catch(() => {
      showError('API not reachable', 'Make sure backend server is running');
    });
});
