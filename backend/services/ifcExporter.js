/**
 * IFC Exporter Service - Phase 6
 * Handles conversion of 3D models and scenes to IFC format
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('./pythonBridge');
const logger = require('../middleware/logger');
const config = require('../config/env');

/**
 * Export single GLB to IFC furniture
 * @param {string} glbPath - Path to GLB file
 * @param {object} objectInfo - Object metadata (name, position, rotation)
 * @param {string} outputDir - Output directory
 * @returns {Promise<object>} - { success, ifcPath, metadata }
 */
async function exportGLBToIFC(glbPath, objectInfo, outputDir) {
  try {
    if (!fs.existsSync(glbPath)) {
      throw new Error(`GLB file not found: ${glbPath}`);
    }

    const timestamp = Date.now();
    const ifcPath = path.join(outputDir, `furniture_${timestamp}.ifc`);
    
    logger.info('IFC_EXPORTER', 'Converting GLB to IFC furniture', { glbPath, ifcPath });

    // Prepare object info JSON
    const objectInfoJSON = JSON.stringify({
      name: objectInfo?.name || 'Furniture',
      position: objectInfo?.position || [0, 0, 0],
      rotation: objectInfo?.rotation || [0, 0, 0],
    });

    // Execute Python script
    const result = await executePythonScript(
      'createIFCFurniture.py',
      [glbPath, ifcPath, objectInfoJSON],
      { timeout: 60000 }
    );

    if (!result.success) {
      throw new Error(result.stderr || 'IFC conversion failed');
    }

    // Verify IFC was created
    if (!fs.existsSync(ifcPath)) {
      throw new Error('IFC file was not created');
    }

    const ifcStats = fs.statSync(ifcPath);
    const metadata = result.stdout?.data || {};

    logger.info('IFC_EXPORTER', 'IFC export complete', {
      ifcPath,
      ifcSize: ifcStats.size,
    });

    return {
      success: true,
      ifcPath: ifcPath,
      ifcUrl: `/outputs/${path.basename(ifcPath)}`,
      metadata: {
        glbSize: fs.statSync(glbPath).size,
        ifcSize: ifcStats.size,
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('IFC_EXPORTER', 'GLB to IFC conversion error', { error: error.message });
    throw error;
  }
}

/**
 * Export scene to combined IFC project
 * @param {Array} sceneObjects - Array of objects with GLB paths and transforms
 * @param {string} outputDir - Output directory
 * @returns {Promise<object>} - { success, ifcPath, metadata }
 */
async function exportSceneToIFC(sceneObjects, outputDir) {
  try {
    if (!Array.isArray(sceneObjects) || sceneObjects.length === 0) {
      throw new Error('No objects to export');
    }

    const timestamp = Date.now();
    const ifcPath = path.join(outputDir, `scene_${timestamp}.ifc`);
    
    logger.info('IFC_EXPORTER', 'Exporting scene to IFC', {
      objectCount: sceneObjects.length,
      ifcPath,
    });

    // Pass entire objects array as one JSON string — avoids shell arg limits
    const objectsJSON = JSON.stringify(sceneObjects.map(obj => ({
      id: obj.id,
      name: obj.name || 'Object',
      position: obj.position || [0, 0, 0],
      rotation: obj.rotation || [0, 0, 0],
      scale: obj.scale || [1, 1, 1],
      glbPath: obj.glbPath || obj.glbUrl || '',
      ifcClass: obj.ifcClass || obj.ifc_class || null,
      category: obj.category || null,
      dimensions: obj.dimensions || null,
      extraMeta: obj.extraMeta || obj.extra_meta || null,
    })));

    const result = await executePythonScript(
      'saveIFC.py',
      [ifcPath, objectsJSON],
      { timeout: 120000 }
    );

    if (!result.success) {
      throw new Error(result.stderr || 'Scene IFC export failed');
    }

    // Verify IFC was created
    if (!fs.existsSync(ifcPath)) {
      throw new Error('IFC file was not created');
    }

    const ifcStats = fs.statSync(ifcPath);
    const metadata = result.stdout?.data || {};

    logger.info('IFC_EXPORTER', 'Scene export complete', {
      ifcPath,
      ifcSize: ifcStats.size,
      objectCount: sceneObjects.length,
    });

    return {
      success: true,
      ifcPath: ifcPath,
      ifcUrl: `/outputs/${path.basename(ifcPath)}`,
      metadata: {
        ifcSize: ifcStats.size,
        objectCount: sceneObjects.length,
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('IFC_EXPORTER', 'Scene export error', { error: error.message });
    throw error;
  }
}

/**
 * Get available IFC export formats
 * @returns {Array} - Supported formats
 */
function getAvailableFormats() {
  return [
    {
      format: 'ifc2x3',
      name: 'IFC 2x3',
      description: 'Industry Foundation Classes 2x3 with furniture elements',
    },
    {
      format: 'ifc4',
      name: 'IFC 4',
      description: 'Industry Foundation Classes 4.0 (future)',
    },
  ];
}

module.exports = {
  exportGLBToIFC,
  exportSceneToIFC,
  getAvailableFormats,
};
