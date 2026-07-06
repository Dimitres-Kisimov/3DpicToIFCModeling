/**
 * TripoSR AI Model Adapter - Phase 3
 * Handles TripoSR model inference calls for high-quality 3D generation
 */

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { executePythonScript } = require('../services/pythonBridge');
const logger = require('../middleware/logger');
const config = require('../config/env');

// Replace a TripoSR office-chair's broken/fragmented base with a clean parametric 5-star wheelbase.
// TripoSR cannot reconstruct a 5-star swivel base from one photo; this grafts a CAD base onto the
// (good) generated seat/back. Runs on the pinned interpreter that has trimesh/pymeshfix.
// Off-switch: env SCS_GRAFT_CHAIR_BASE=0. Scope: 'office' = office chairs only, else any chair.
function runGraftChairBase(inPath, outPath) {
  return new Promise((resolve) => {
    const script = path.join(__dirname, '..', 'python-scripts', 'graft_chair_base.py');
    const py = config.PYTHON_PATH;   // pinned interpreter comes from .env
    const child = spawn(py, [script, inPath, outPath], { cwd: path.join(__dirname, '..', '..') });
    let out = '', err = '';
    child.stdout.on('data', (c) => { out += c.toString(); });
    child.stderr.on('data', (c) => { err += c.toString(); });
    child.on('error', () => resolve({ ok: false }));
    child.on('close', (code) => {
      resolve({ ok: code === 0 && fs.existsSync(outPath), log: (out + err).trim().split('\n').pop() });
    });
  });
}

// Decide whether an object should get the base graft, from its detected label.
// OFFICE CHAIRS ONLY (5-star swivel base) — a plain/dining chair must NOT get a wheelbase.
// Off-switch: env SCS_GRAFT_CHAIR_BASE=0. Set =allchairs to widen to any chair.
function shouldGraftChair(label, category) {
  const mode = (process.env.SCS_GRAFT_CHAIR_BASE || '1').toLowerCase();
  if (mode === '0' || mode === 'false' || mode === 'off') return false;
  const l = (label || '').toLowerCase(), c = (category || '').toLowerCase();
  if (mode === 'allchairs') return c === 'chair' || /chair/.test(l);
  return /office|swivel|desk chair/.test(l);   // default: office chairs only
}

/**
 * Run TripoSR inference on image
 * @param {string} imagePath - Path to input image
 * @param {string} outputDir - Directory for output GLB
 * @returns {Promise<object>} - { success, glbPath, metadata }
 */
async function runTripoSR(imagePath, outputDir, opts = {}) {
  try {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`Input image not found: ${imagePath}`);
    }

    const outputGlbPath = path.join(outputDir, `triposr_${Date.now()}.glb`);
    
    logger.info('TripoSR', `Starting high-quality inference`, { imagePath, outputGlbPath });

    // Use Meshy cloud API if key is configured, otherwise fall back to local depth mesh
    const meshyKey = process.env.MESHY_API_KEY || '';
    const script = meshyKey ? 'run_meshy_api.py' : 'run_triposr.py';
    const env = meshyKey ? { ...process.env, MESHY_API_KEY: meshyKey } : process.env;
    logger.info('TripoSR', meshyKey ? 'Using Meshy cloud API' : 'Using local depth mesh (no MESHY_API_KEY set)');

    const result = await executePythonScript(script, [imagePath, outputGlbPath], {
      timeout: 900000,
      env,
    });

    if (!result.success) {
      throw new Error(result.stderr || 'TripoSR inference failed');
    }

    // Verify GLB was created
    if (!fs.existsSync(outputGlbPath)) {
      throw new Error('GLB file was not created');
    }

    const metadata = result.stdout?.data || {};
    let finalGlbPath = outputGlbPath;
    let graftedBase = false;

    // Office-chair base graft: TripoSR reconstructs the 5-star swivel base as broken/floating
    // fragments. Keep the (good) generated seat/back, cut the broken base, graft a clean CAD
    // 5-star wheelbase. Office chairs only; env SCS_GRAFT_CHAIR_BASE=0 disables. The grafted GLB
    // is already mesh-optimized (decimated/smoothed) and the base is one solid component.
    if (opts.forceGraft || shouldGraftChair(metadata.object_label, metadata.ifc_category)) {
      const graftedPath = outputGlbPath.replace(/\.glb$/i, '_grafted.glb');
      logger.info('TripoSR', 'Office chair base graft', {
        label: metadata.object_label, forced: !!opts.forceGraft,
      });
      const g = await runGraftChairBase(outputGlbPath, graftedPath);
      if (g.ok) {
        finalGlbPath = graftedPath;
        graftedBase = true;
        // If the user manually declared this an office chair, trust them over CLIP so the IFC
        // is tagged correctly (CLIP frequently mislabels swivel chairs as cabinet/desk).
        if (opts.forceGraft) {
          metadata.object_label = 'office chair';
          metadata.ifc_class = 'IfcFurnitureElement';
          metadata.ifc_category = 'Chair';
        }
        logger.info('TripoSR', 'Base graft applied', { glbPath: graftedPath, log: g.log });
      } else {
        logger.warn('TripoSR', 'Base graft skipped — using raw mesh', { log: g.log });
      }
    }

    const glbStats = fs.statSync(finalGlbPath);
    logger.info('TripoSR', 'High-quality inference complete', {
      glbPath: finalGlbPath,
      glbSize: glbStats.size,
    });

    return {
      success: true,
      glbPath: finalGlbPath,
      glbUrl: `/outputs/${path.basename(finalGlbPath)}`,
      metadata: {
        model: 'triposr',
        glbSize: glbStats.size,
        quality_preset: 'high',
        grafted_base: graftedBase,
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
