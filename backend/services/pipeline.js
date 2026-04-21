/**
 * Pipeline Service - Phase 7
 * Orchestrates the complete workflow: Image → 3D → Processing → IFC Export
 */

const path = require('path');
const fs = require('fs');
const logger = require('../middleware/logger');

// Import all services
const aiAdapters = {
  instantmesh: require('../ai/instantMesh'),
  stablefast3d: require('../ai/stablefast3d'),
  triposr: require('../ai/triposr'),
};
const meshProcessor = require('./meshProcessor');
const ifcExporter = require('./ifcExporter');

/**
 * Complete pipeline: Image → GLB → Process → IFC
 * @param {string} imagePath - Input image path
 * @param {string} model - AI model to use (instantmesh, stablefast3d, triposr)
 * @param {object} options - Pipeline options
 * @returns {Promise<object>} - Complete pipeline result
 */
async function runFullPipeline(imagePath, model, options = {}) {
  try {
    const startTime = Date.now();
    const outputDir = options.outputDir || './outputs';

    logger.info('PIPELINE', 'Starting full pipeline', {
      image: imagePath,
      model: model,
    });

    // Step 1: Generate 3D model using AI
    logger.info('PIPELINE', 'Step 1/4: Generating 3D model with ' + model);
    const aiAdapter = aiAdapters[model.toLowerCase()];
    
    if (!aiAdapter) {
      throw new Error(`Unknown AI model: ${model}`);
    }

    let aiResult;
    switch (model.toLowerCase()) {
      case 'instantmesh':
        aiResult = await aiAdapter.runInstantMesh(imagePath, outputDir);
        break;
      case 'stablefast3d':
        aiResult = await aiAdapter.runStableFast3D(imagePath, outputDir);
        break;
      case 'triposr':
        aiResult = await aiAdapter.runTripoSR(imagePath, outputDir);
        break;
    }

    const generatedGLB = aiResult.glbPath;
    logger.info('PIPELINE', 'Step 1 complete: GLB generated', {
      glbPath: generatedGLB,
      glbSize: aiResult.metadata.glbSize,
    });

    // Step 2: Process mesh (clean, normalize, fix orientation)
    if (options.processMesh !== false) {
      logger.info('PIPELINE', 'Step 2/4: Processing mesh');
      
      const processResult = await meshProcessor.processMeshPipeline(generatedGLB, outputDir);
      
      logger.info('PIPELINE', 'Step 2 complete: Mesh processed', {
        glbPath: processResult.glbPath,
        glbSize: processResult.metadata.glbSize,
      });

      // Replace GLB with processed version
      aiResult.glbPath = processResult.glbPath;
      aiResult.glbUrl = processResult.glbUrl;
      aiResult.metadata.processed = true;
    }

    // Step 3: Export to IFC if requested
    let ifcResult = null;
    if (options.exportIFC !== false) {
      logger.info('PIPELINE', 'Step 3/4: Exporting to IFC');

      const objectInfo = {
        name: options.objectName || `${model} Generated Object`,
        position: options.position || [0, 0, 0],
        rotation: options.rotation || [0, 0, 0],
      };

      ifcResult = await ifcExporter.exportGLBToIFC(
        aiResult.glbPath,
        objectInfo,
        outputDir
      );

      logger.info('PIPELINE', 'Step 3 complete: IFC exported', {
        ifcPath: ifcResult.ifcPath,
        ifcSize: ifcResult.metadata.ifcSize,
      });
    }

    // Step 4: Generate summary
    const duration = Date.now() - startTime;
    logger.info('PIPELINE', 'Step 4/4: Generating summary');

    const summary = {
      success: true,
      model: model,
      duration_ms: duration,
      steps: {
        ai_generation: {
          status: 'complete',
          glbPath: aiResult.glbPath,
          glbUrl: aiResult.glbUrl,
          glbSize: aiResult.metadata.glbSize,
        },
        mesh_processing: options.processMesh !== false ? {
          status: 'complete',
          processed: true,
        } : {
          status: 'skipped',
          processed: false,
        },
        ifc_export: ifcResult ? {
          status: 'complete',
          ifcPath: ifcResult.ifcPath,
          ifcUrl: ifcResult.ifcUrl,
          ifcSize: ifcResult.metadata.ifcSize,
        } : {
          status: 'skipped',
          ifcPath: null,
        },
      },
      output: {
        glbUrl: aiResult.glbUrl,
        ifcUrl: ifcResult?.ifcUrl || null,
      },
    };

    logger.info('PIPELINE', 'Pipeline complete', {
      duration: `${(duration / 1000).toFixed(2)}s`,
      glbUrl: aiResult.glbUrl,
      ifcUrl: ifcResult?.ifcUrl || null,
    });

    return summary;
  } catch (error) {
    logger.error('PIPELINE', 'Pipeline error', { error: error.message });
    throw error;
  }
}

/**
 * Get pipeline status/info
 * @returns {object} - Pipeline information
 */
function getPipelineInfo() {
  return {
    name: '3D Picture to IFC Modeling Pipeline',
    version: '1.0.0',
    phases: [
      {
        name: 'AI Generation',
        models: ['instantmesh', 'stablefast3d', 'triposr'],
        description: 'Generate 3D mesh from 2D image',
      },
      {
        name: 'Mesh Processing',
        operations: ['clean', 'normalize', 'orient', 'convert_to_glb'],
        description: 'Process and optimize mesh geometry',
      },
      {
        name: 'IFC Export',
        formats: ['ifc2x3', 'ifc4'],
        description: 'Export to IFC building format',
      },
    ],
    status: 'operational',
  };
}

module.exports = {
  runFullPipeline,
  getPipelineInfo,
};
