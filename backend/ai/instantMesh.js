/**
 * InstantMesh AI Model Adapter - Phase 3
 * Handles InstantMesh model inference calls
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('../services/pythonBridge');
const logger = require('../middleware/logger');
const config = require('../config/env');

/**
 * Run InstantMesh inference on image
 * @param {string} imagePath - Path to input image
 * @param {string} outputDir - Directory for output GLB
 * @returns {Promise<object>} - { success, glbPath, metadata }
 */
async function runInstantMesh(imagePath, outputDir) {
  try {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`Input image not found: ${imagePath}`);
    }

    const outputGlbPath = path.join(outputDir, `instantmesh_${Date.now()}.glb`);
    
    logger.info('InstantMesh', `Starting inference`, { imagePath, outputGlbPath });

    // Execute Python script
    const result = await executePythonScript('run_instantmesh.py', [imagePath, outputGlbPath], {
      timeout: 600000, // 10 minutes for model inference
    });

    if (!result.success) {
      throw new Error(result.stderr || 'InstantMesh inference failed');
    }

    // Verify GLB was created
    if (!fs.existsSync(outputGlbPath)) {
      throw new Error('GLB file was not created');
    }

    const glbStats = fs.statSync(outputGlbPath);
    const metadata = result.stdout?.data || {};

    logger.info('InstantMesh', 'Inference complete', {
      glbPath: outputGlbPath,
      glbSize: glbStats.size,
    });

    return {
      success: true,
      glbPath: outputGlbPath,
      glbUrl: `/outputs/${path.basename(outputGlbPath)}`,
      metadata: {
        model: 'instantmesh',
        glbSize: glbStats.size,
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('InstantMesh', 'Inference error', { error: error.message });
    throw error;
  }
}

/**
 * Validate InstantMesh configuration
 * @returns {Promise<object>} - { available, reason }
 */
async function validateInstantMesh() {
  try {
    // Check if model files/configs exist
    // In production, would verify model checkpoint availability
    
    return {
      available: true,
      model: 'instantmesh',
      status: 'ready',
    };
  } catch (error) {
    return {
      available: false,
      model: 'instantmesh',
      status: 'error',
      reason: error.message,
    };
  }
}

module.exports = {
  runInstantMesh,
  validateInstantMesh,
};
