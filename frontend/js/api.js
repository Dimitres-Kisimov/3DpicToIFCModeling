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

async function generateModel(imageBlob, modelName) {
  try {
    const formData = new FormData();
    formData.append('image', imageBlob, 'uploaded_image');
    formData.append('model', modelName);

    updateStatus(`Generating 3D model using ${modelName}...`);

    const response = await fetch(`${API_BASE}/generate`, {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error?.message || 'Generation failed');
    }

    showSuccess(`Model generated successfully`);
    return data.glb;
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
