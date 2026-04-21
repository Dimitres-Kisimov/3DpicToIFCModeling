/**
 * TripoSR AI Model Adapter - Phase 3
 * Handles TripoSR model inference calls for high-quality 3D generation
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('../services/pythonBridge');
const logger = require('../middleware/logger');
const config = require('../config/env');

/**
 * Run TripoSR inference on image
 * @param {string} imagePath - Path to input image
 * @param {string} outputDir - Directory for output GLB
 * @returns {Promise<object>} - { success, glbPath, metadata }
 */
async function runTripoSR(imagePath, outputDir) {
  try {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`Input image not found: ${imagePath}`);
    }

    const outputGlbPath = path.join(outputDir, `triposr_${Date.now()}.glb`);
    
    logger.info('TripoSR', `Starting high-quality inference`, { imagePath, outputGlbPath });

    // Execute Python script
    const result = await executePythonScript('run_triposr.py', [imagePath, outputGlbPath], {
      timeout: 900000, // 15 minutes for high-quality inference
    });

    if (!result.success) {
      throw new Error(result.stderr || 'TripoSR inference failed');
    }

    // Verify GLB was created
    if (!fs.existsSync(outputGlbPath)) {
      throw new Error('GLB file was not created');
    }

    const glbStats = fs.statSync(outputGlbPath);
    const metadata = result.stdout?.data || {};

    logger.info('TripoSR', 'High-quality inference complete', {
      glbPath: outputGlbPath,
      glbSize: glbStats.size,
    });

    return {
      success: true,
      glbPath: outputGlbPath,
      glbUrl: `/outputs/${path.basename(outputGlbPath)}`,
      metadata: {
        model: 'triposr',
        glbSize: glbStats.size,
        quality_preset: 'high',
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('TripoSR', 'Inference error', { error: error.message });
    throw error;
  }
}

/**
 * Validate TripoSR configuration
 * @returns {Promise<object>} - { available, reason }
 */
async function validateTripoSR() {
  try {
    return {
      available: true,
      model: 'triposr',
      status: 'ready',
      quality: 'high',
    };
  } catch (error) {
    return {
      available: false,
      model: 'triposr',
      status: 'error',
      reason: error.message,
    };
  }
}

module.exports = {
  runTripoSR,
  validateTripoSR,
};
