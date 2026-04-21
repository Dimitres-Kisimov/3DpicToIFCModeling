/**
 * Mesh Processor Service - Phase 4
 * Handles mesh processing pipeline (clean, normalize, fix orientation, convert to GLB)
 */

const path = require('path');
const fs = require('fs');
const { executePythonScript } = require('./pythonBridge');
const logger = require('../middleware/logger');
const config = require('../config/env');

/**
 * Full mesh processing pipeline
 * @param {string} inputMeshPath - Path to input mesh file
 * @param {string} outputDir - Directory for output files
 * @returns {Promise<object>} - { success, glbPath, metadata }
 */
async function processMeshPipeline(inputMeshPath, outputDir) {
  try {
    if (!fs.existsSync(inputMeshPath)) {
      throw new Error(`Input mesh not found: ${inputMeshPath}`);
    }

    logger.info('MESH_PROCESSOR', 'Starting mesh processing pipeline', { inputMeshPath });

    const timestamp = Date.now();
    const cleanedPath = path.join(outputDir, `mesh_cleaned_${timestamp}.mesh`);
    const normalizedPath = path.join(outputDir, `mesh_normalized_${timestamp}.mesh`);
    const orientedPath = path.join(outputDir, `mesh_oriented_${timestamp}.mesh`);
    const glbPath = path.join(outputDir, `processed_${timestamp}.glb`);

    // Step 1: Clean mesh
    logger.info('MESH_PROCESSOR', 'Step 1/4: Cleaning mesh');
    let cleanResult = await executePythonScript('cleanMesh.py', [inputMeshPath, cleanedPath], {
      timeout: 60000,
    });
    if (!cleanResult.success) {
      throw new Error(`Mesh cleaning failed: ${cleanResult.stderr}`);
    }

    // Step 2: Normalize mesh
    logger.info('MESH_PROCESSOR', 'Step 2/4: Normalizing mesh');
    let normalResult = await executePythonScript('normalizeMesh.py', [cleanedPath, normalizedPath, '1.0'], {
      timeout: 60000,
    });
    if (!normalResult.success) {
      throw new Error(`Mesh normalization failed: ${normalResult.stderr}`);
    }

    // Step 3: Fix orientation
    logger.info('MESH_PROCESSOR', 'Step 3/4: Fixing mesh orientation');
    let orientResult = await executePythonScript('fixOrientation.py', [normalizedPath, orientedPath], {
      timeout: 60000,
    });
    if (!orientResult.success) {
      throw new Error(`Mesh orientation fixing failed: ${orientResult.stderr}`);
    }

    // Step 4: Convert to GLB
    logger.info('MESH_PROCESSOR', 'Step 4/4: Converting to GLB');
    let glbResult = await executePythonScript('meshToGLB.py', [orientedPath, glbPath], {
      timeout: 60000,
    });
    if (!glbResult.success) {
      throw new Error(`GLB conversion failed: ${glbResult.stderr}`);
    }

    // Verify final GLB was created
    if (!fs.existsSync(glbPath)) {
      throw new Error('Final GLB file was not created');
    }

    const glbStats = fs.statSync(glbPath);

    // Cleanup intermediate files
    [cleanedPath, normalizedPath, orientedPath].forEach(file => {
      try {
        if (fs.existsSync(file)) {
          fs.unlinkSync(file);
        }
      } catch (e) {
        logger.warn('MESH_PROCESSOR', 'Failed to cleanup intermediate file', { file });
      }
    });

    logger.info('MESH_PROCESSOR', 'Mesh processing pipeline complete', {
      glbPath,
      glbSize: glbStats.size,
    });

    return {
      success: true,
      glbPath: glbPath,
      glbUrl: `/outputs/${path.basename(glbPath)}`,
      metadata: {
        processedAt: new Date().toISOString(),
        glbSize: glbStats.size,
        pipeline_stages: 4,
        stages: [
          cleanResult.stdout?.data || {},
          normalResult.stdout?.data || {},
          orientResult.stdout?.data || {},
          glbResult.stdout?.data || {},
        ],
      },
    };
  } catch (error) {
    logger.error('MESH_PROCESSOR', 'Pipeline error', { error: error.message });
    throw error;
  }
}

/**
 * Individual mesh processing step
 * @param {string} operation - clean, normalize, orient, to_glb
 * @param {string} inputPath - Input mesh path
 * @param {string} outputPath - Output path
 * @param {object} options - Additional options
 * @returns {Promise<object>}
 */
async function processMeshStep(operation, inputPath, outputPath, options = {}) {
  try {
    let result;

    switch (operation) {
      case 'clean':
        result = await executePythonScript('cleanMesh.py', [inputPath, outputPath]);
        break;
      case 'normalize':
        const targetSize = options.targetSize || 1.0;
        result = await executePythonScript('normalizeMesh.py', [inputPath, outputPath, targetSize.toString()]);
        break;
      case 'orient':
        result = await executePythonScript('fixOrientation.py', [inputPath, outputPath]);
        break;
      case 'to_glb':
        result = await executePythonScript('meshToGLB.py', [inputPath, outputPath]);
        break;
      default:
        throw new Error(`Unknown operation: ${operation}`);
    }

    if (!result.success) {
      throw new Error(result.stderr || `${operation} failed`);
    }

    return {
      success: true,
      operation,
      input: inputPath,
      output: outputPath,
      metadata: result.stdout?.data || {},
    };
  } catch (error) {
    logger.error('MESH_PROCESSOR', `Operation ${operation} failed`, { error: error.message });
    throw error;
  }
}

module.exports = {
  processMeshPipeline,
  processMeshStep,
};
