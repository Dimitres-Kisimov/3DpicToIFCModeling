/**
 * Transform Controls Module - Phase 5 (preview for Phase 2)
 * Handles object positioning, rotation, and scaling
 */

let selectedObjectId = null;

/**
 * Set selected object
 * @param {string} objectId - Object ID
 */
function setSelectedObject(objectId) {
  selectedObjectId = objectId;
  console.log('[transformControls] Selected object:', objectId);

  // Show transform panel
  const panel = document.getElementById('transformPanel');
  if (panel) {
    panel.style.display = 'block';
    updateTransformUI();
  }
}

/**
 * Get selected object
 * @returns {string} - Selected object ID
 */
function getSelectedObject() {
  return selectedObjectId;
}

/**
 * Move object by delta
 * @param {string} objectId - Object ID
 * @param {Array} deltaPos - [dx, dy, dz]
 */
function moveObject(objectId, deltaPos) {
  const viewer = window.xeokitModule.getViewer();
  if (!viewer) return;

  const entity = viewer.scene.entities[objectId];
  if (!entity) return;

  const pos = entity.position || [0, 0, 0];
  const newPos = [pos[0] + deltaPos[0], pos[1] + deltaPos[1], pos[2] + deltaPos[2]];

  window.xeokitModule.updateObjectTransform(objectId, newPos);
  console.log('[transformControls] Moved object:', objectId, newPos);
}

/**
 * Rotate object by delta (degrees)
 * @param {string} objectId - Object ID
 * @param {Array} deltaRot - [dx, dy, dz] in degrees
 */
function rotateObject(objectId, deltaRot) {
  const viewer = window.xeokitModule.getViewer();
  if (!viewer) return;

  const entity = viewer.scene.entities[objectId];
  if (!entity) return;

  const rot = entity.rotation || [0, 0, 0];
  const rotDeg = [(rot[0] * 180) / Math.PI, (rot[1] * 180) / Math.PI, (rot[2] * 180) / Math.PI];

  const newRotDeg = [rotDeg[0] + deltaRot[0], rotDeg[1] + deltaRot[1], rotDeg[2] + deltaRot[2]];

  window.xeokitModule.updateObjectTransform(objectId, null, newRotDeg);
  console.log('[transformControls] Rotated object:', objectId, newRotDeg);
}

/**
 * Snap object to ground (Y=0)
 * @param {string} objectId - Object ID
 */
function snapToGround(objectId) {
  const viewer = window.xeokitModule.getViewer();
  if (!viewer) return;

  const entity = viewer.scene.entities[objectId];
  if (!entity) return;

  const pos = entity.position || [0, 0, 0];
  const newPos = [pos[0], 0, pos[2]];

  window.xeokitModule.updateObjectTransform(objectId, newPos);
  console.log('[transformControls] Snapped to ground:', objectId);
  updateStatus('✓ Snapped to ground');
}

/**
 * Reset object transform
 * @param {string} objectId - Object ID
 */
function resetTransform(objectId) {
  window.xeokitModule.updateObjectTransform(objectId, [0, 0, 0], [0, 0, 0], [1, 1, 1]);
  console.log('[transformControls] Reset transform:', objectId);
  updateStatus('✓ Transform reset');
}

/**
 * Update transform UI with current values
 */
function updateTransformUI() {
  if (!selectedObjectId) return;

  const viewer = window.xeokitModule.getViewer();
  if (!viewer) return;

  const entity = viewer.scene.entities[selectedObjectId];
  if (!entity) return;

  const pos = entity.position || [0, 0, 0];
  const rot = entity.rotation || [0, 0, 0];
  const rotDeg = [(rot[0] * 180) / Math.PI, (rot[1] * 180) / Math.PI, (rot[2] * 180) / Math.PI];

  document.getElementById('posX').value = pos[0].toFixed(2);
  document.getElementById('posY').value = pos[1].toFixed(2);
  document.getElementById('posZ').value = pos[2].toFixed(2);

  document.getElementById('rotX').value = rotDeg[0].toFixed(1);
  document.getElementById('rotY').value = rotDeg[1].toFixed(1);
  document.getElementById('rotZ').value = rotDeg[2].toFixed(1);
}

/**
 * Apply transform from UI inputs
 */
function applyTransformFromUI() {
  if (!selectedObjectId) return;

  const pos = [
    parseFloat(document.getElementById('posX').value || 0),
    parseFloat(document.getElementById('posY').value || 0),
    parseFloat(document.getElementById('posZ').value || 0),
  ];

  const rot = [
    parseFloat(document.getElementById('rotX').value || 0),
    parseFloat(document.getElementById('rotY').value || 0),
    parseFloat(document.getElementById('rotZ').value || 0),
  ];

  window.xeokitModule.updateObjectTransform(selectedObjectId, pos, rot);
  console.log('[transformControls] Applied transform from UI');
}

// Export functions
window.transformModule = {
  setSelectedObject,
  getSelectedObject,
  moveObject,
  rotateObject,
  snapToGround,
  resetTransform,
  updateTransformUI,
  applyTransformFromUI,
};
