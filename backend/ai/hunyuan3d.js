/**
 * Hunyuan3D-2 AI Model Adapter - Sprint 7
 * Tencent/Hunyuan3D-2 — Community License (commercial with attribution)
 * Multi-view diffusion + texture bake pipeline
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('../services/pythonBridge');
const logger = require('../middleware/logger');

async function runHunyuan3D(imagePath, outputDir) {
  try {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`Input image not found: ${imagePath}`);
    }

    const outputGlbPath = path.join(outputDir, `hunyuan3d_${Date.now()}.glb`);
    logger.info('Hunyuan3D', 'Starting inference', { imagePath, outputGlbPath });

    const result = await executePythonScript('run_hunyuan3d.py', [imagePath, outputGlbPath], {
      timeout: 1200000,  // 20 min — texture bake is slow on CPU
    });

    if (!result.success) {
      throw new Error(result.stderr || 'Hunyuan3D-2 inference failed');
    }
    if (!fs.existsSync(outputGlbPath)) {
      throw new Error('GLB file was not created');
    }

    const glbStats = fs.statSync(outputGlbPath);
    const metadata = result.stdout?.data || {};

    logger.info('Hunyuan3D', 'Inference complete', { glbPath: outputGlbPath, glbSize: glbStats.size });

    return {
      success: true,
      glbPath: outputGlbPath,
      glbUrl: `/outputs/${path.basename(outputGlbPath)}`,
      metadata: {
        model: 'hunyuan3d-2',
        glbSize: glbStats.size,
        license: 'Community (commercial with attribution)',
        ...metadata,
      },
    };
  } catch (error) {
    logger.error('Hunyuan3D', 'Inference error', { error: error.message });
    throw error;
  }
}

module.exports = { runHunyuan3D };
