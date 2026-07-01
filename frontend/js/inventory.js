/**
 * Inventory System - Phase 2
 * Manages generated 3D objects and their metadata
 */

const inventory = [];
let nextInventoryId = 1;

/**
 * Add object to inventory
 * @param {object} item - Item to add
 * @returns {object} - Added item with ID
 */
function addToInventory(item) {
  const inventoryItem = {
    id: item.id || `inv_${nextInventoryId++}`,
    name: item.name || `Object ${nextInventoryId}`,
    modelType: item.modelType || 'unknown',
    category: item.category || null,
    ifcClass: item.ifcClass || null,
    confidence: item.confidence ?? null,
    cocoLabel: item.cocoLabel || null,
    dimensions: item.dimensions || null,
    glbPath: item.glbPath,
    glbUrl: item.glbUrl,
    position: item.position || [0, 0, 0],
    rotation: item.rotation || [0, 0, 0],
    scale: item.scale || [1, 1, 1],
    metadata: item.metadata || {},
    dateAdded: new Date().toISOString(),
    thumbnail: item.thumbnail || null,
  };

  inventory.push(inventoryItem);
  console.log('[inventory] Added item:', inventoryItem.id);
  updateInventoryUI();

  return inventoryItem;
}

/**
 * Get all inventory items
 * @returns {Array} - Inventory items
 */
function getInventory() {
  return inventory;
}

/**
 * Get single inventory item
 * @param {string} itemId - Item ID
 * @returns {object} - Inventory item or null
 */
function getInventoryItem(itemId) {
  return inventory.find((item) => item.id === itemId);
}

/**
 * Remove item from inventory
 * @param {string} itemId - Item ID
 */
function removeFromInventory(itemId) {
  const index = inventory.findIndex((item) => item.id === itemId);
  if (index !== -1) {
    inventory.splice(index, 1);
    console.log('[inventory] Removed item:', itemId);
    updateInventoryUI();
  }
}

/**
 * Spawn object from inventory into scene
 * @param {string} itemId - Item ID
 * @param {string} newObjectId - New object ID in scene
 * @returns {Promise<object>} - Loaded entity
 */
async function spawnFromInventory(itemId, newObjectId) {
  const item = getInventoryItem(itemId);
  if (!item) {
    showError(`Item not found in inventory: ${itemId}`);
    return null;
  }

  try {
    updateStatus(`Spawning ${item.name} into scene...`);

    // Load into viewer with new ID
    const entity = await window.glbLoaderModule.addGLBToViewer(item.glbUrl, newObjectId);

    // Apply stored transforms
    if (entity) {
      window.xeokitModule.updateObjectTransform(newObjectId, item.position, item.rotation, item.scale);
    }

    updateStatus(`✓ Spawned ${item.name}`);
    return entity;
  } catch (error) {
    showError('Failed to spawn from inventory', error);
    throw error;
  }
}

/**
 * Update inventory item
 * @param {string} itemId - Item ID
 * @param {object} updates - Properties to update
 */
function updateInventoryItem(itemId, updates) {
  const item = getInventoryItem(itemId);
  if (item) {
    Object.assign(item, updates);
    console.log('[inventory] Updated item:', itemId);
    updateInventoryUI();
  }
}

/**
 * Clear entire inventory
 */
function clearInventory() {
  inventory.length = 0;
  nextInventoryId = 1;
  console.log('[inventory] Inventory cleared');
  updateInventoryUI();
}

/**
 * Export inventory to JSON
 * @returns {string} - JSON string
 */
function exportInventoryJSON() {
  return JSON.stringify(inventory, null, 2);
}

/**
 * Import inventory from JSON
 * @param {string} jsonString - JSON inventory data
 */
function importInventoryJSON(jsonString) {
  try {
    const imported = JSON.parse(jsonString);
    if (Array.isArray(imported)) {
      inventory.length = 0;
      inventory.push(...imported);
      updateInventoryUI();
      console.log('[inventory] Imported items:', imported.length);
    }
  } catch (error) {
    showError('Failed to import inventory', error);
  }
}

/**
 * Update inventory UI display
 */
function updateInventoryUI() {
  const inventoryList = document.getElementById('inventoryList');
  if (!inventoryList) return;

  const countEl = document.getElementById('invCount');
  if (countEl) countEl.textContent = inventory.length;

  if (inventory.length === 0) {
    inventoryList.innerHTML = '<p class="empty-state">No objects in inventory</p>';
    return;
  }

  const rows = inventory
    .map((item) => {
      const dims = item.dimensions || {};
      const dimsStr = (dims.height && dims.width && dims.depth)
        ? `${dims.height.toFixed(2)} × ${dims.width.toFixed(2)} × ${dims.depth.toFixed(2)} m`
        : '—';
      const conf = item.confidence != null ? `${(item.confidence * 100).toFixed(0)}%` : '—';
      const ifcClass = item.ifcClass || '—';
      const category = item.category || item.modelType || '—';
      return `
        <tr>
          <td><strong>${category.replace(/_/g, ' ')}</strong></td>
          <td><code>${ifcClass}</code></td>
          <td>${conf}</td>
          <td>${dimsStr}</td>
          <td>
            <button class="btn btn-small" onclick="window.inventoryModule.spawnFromInventory('${item.id}', 'obj_' + Date.now())">Spawn</button>
            <button class="btn btn-small" onclick="window.inventoryModule.removeFromInventory('${item.id}'); window.inventoryModule.refreshUI && window.inventoryModule.refreshUI();">Remove</button>
          </td>
        </tr>`;
    })
    .join('');

  inventoryList.innerHTML = `
    <table class="inventory-table">
      <thead>
        <tr>
          <th>Category</th>
          <th>IFC class</th>
          <th>Conf.</th>
          <th>H × W × D</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  console.log('[inventory] UI updated, items:', inventory.length);
}

// Export functions
window.inventoryModule = {
  addToInventory,
  getInventory,
  getInventoryItem,
  removeFromInventory,
  spawnFromInventory,
  updateInventoryItem,
  clearInventory,
  exportInventoryJSON,
  importInventoryJSON,
};
