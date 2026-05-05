/**
 * TRELLIS AI Model Adapter - Sprint 2
 * Microsoft/TRELLIS — MIT license
 * Structured LATent (SLAT) image-to-3D diffusion
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('../services/pythonBridge');
const logger = require('../middleware/logger');

async function runTRELLIS(imagePath, outputDir) {
  try {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`Input image not found: ${imagePath}`);
    }

    const outputGlbPath = path.join(outputDir, `trellis_${Date.now()}.glb`);
    logger.info('TRELLIS', 'Starting SLAT diffusion inference', { imagePath, outputGlbPath });

    const result = await executePythonScript('run_trellis.py', [imagePath, outputGlbPath], {
      timeout: 900000,
    });

    if (!result.success) {
      throw new Error(result.stderr || 'TRELLIS inference failed');
    }
    if (!fs.existsSync(outputGlbPath)) {
      throw new Error('GLB file was not created');
    }

    const glbStats = fs.statSync(outputGlbPath);
    const metadata = result.stdout?.data || {};

    logger.info('TRELLIS', 'Inference complete', { glbPath: outputGlbPath, glbSize: glbStats.size });

    return {
      success: true,
      glbPath: outputGlbPath,
      glbUrl: `/outputs/${path.basename(outputGlbPath)}`,
      metadata: {
        model: 'trellis',
        glbSize: glbStats.size,
        license: 'MIT',
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('TRELLIS', 'Inference error', { error: error.message });
    throw error;
  }
}

module.exports = { runTRELLIS };
