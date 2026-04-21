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
    id: `inv_${nextInventoryId++}`,
    name: item.name || `Object ${nextInventoryId}`,
    modelType: item.modelType || 'unknown',
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

  if (inventory.length === 0) {
    inventoryList.innerHTML = '<p class="empty-state">No objects in inventory</p>';
    return;
  }

  inventoryList.innerHTML = inventory
    .map(
      (item) => `
    <div class="inventory-item">
      <div>
        <strong>${item.name}</strong>
        <small>${item.modelType}</small>
      </div>
      <div>
        <button class="btn btn-small" onclick="spawnFromInventory('${item.id}', 'obj_${Date.now()}')">
          Spawn
        </button>
        <button class="btn btn-small" onclick="removeFromInventory('${item.id}')">
          Remove
        </button>
      </div>
    </div>
  `
    )
    .join('');

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
