/**
 * API Routes - Generate 3D Models - Phase 3
 * Handles POST /api/generate endpoint
 */

const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const router = express.Router();

const { spawn } = require('child_process');
const logger = require('../middleware/logger');
const config = require('../config/env');

// Import AI model adapters (kept for compatibility but currently broken on
// transformers 5.10.2 — see Appendix E of TECHNICAL_REPORT_SCS.md).
const instantMeshAdapter = require('../ai/instantMesh');
const stableFast3DAdapter = require('../ai/stablefast3d');
const triposrAdapter = require('../ai/triposr');

/**
 * Working pipeline: DETR detection -> category-keyed primitive mesh -> GLB.
 * Replaces the broken TripoSR/InstantMesh/StableFast3D adapters.
 */
function runDetectAndPlace(imagePath, outputDir) {
  return new Promise((resolve, reject) => {
    const outputName = `mesh_${Date.now()}.glb`;
    const outputGlb = path.join(outputDir, outputName);
    const script = path.join(__dirname, '..', 'python-scripts', 'run_detect_and_place.py');
    const pythonPath = config.PYTHON_PATH || 'python';

    const child = spawn(pythonPath, [script, imagePath, outputGlb], {
      cwd: path.join(__dirname, '..', '..'),
      // keep the LIGHT cleanup only (debris filter keeps legs). MIRROR removed — it deleted the
      // chair legs by mirroring the body half over the base. Base cleanup needs a safer approach.
      env: { ...process.env, SCS_TRIPOSR_SKIP_POSTPROC: '1', SCS_TRIPOSR_MIRROR: '0' },
    });

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        logger.error('PIPELINE', 'detect_and_place exited non-zero', { code, stderr: stderr.slice(-800) });
        return reject(new Error(`detect_and_place failed: ${stderr.slice(-300) || stdout.slice(-300)}`));
      }
      const lastLine = stdout.trim().split('\n').filter(Boolean).pop();
      if (!lastLine) return reject(new Error('detect_and_place produced no output'));
      try {
        const parsed = JSON.parse(lastLine);
        if (!parsed.success) {
          return reject(new Error(parsed.error?.message || 'detect_and_place reported failure'));
        }
        parsed.glbUrl = `/outputs/${outputName}`;
        parsed.glbPath = parsed.output_path;
        resolve(parsed);
      } catch (e) {
        reject(new Error(`Failed to parse Python output: ${e.message}\nOutput: ${lastLine.slice(0, 500)}`));
      }
    });
  });
}

// ============================================================================
// MULTER CONFIGURATION - Image Upload
// ============================================================================

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, config.UPLOAD_DIR);
  },
  filename: (req, file, cb) => {
    const uniqueName = `${Date.now()}-${Math.random().toString(36).substring(7)}-${file.originalname}`;
    cb(null, uniqueName);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: config.MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    const allowedMimes = ['image/jpeg', 'image/png', 'image/webp'];
    if (allowedMimes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Only JPEG, PNG, WebP images are allowed'));
    }
  },
});

// ============================================================================
// POST /api/generate - Generate 3D model from image
// ============================================================================

router.post('/generate', upload.single('image'), async (req, res, next) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'MISSING_IMAGE',
          message: 'No image file provided',
        },
      });
    }

    const { model } = req.body;
    if (!model) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'MISSING_MODEL',
          message: 'Model selection required (instantmesh, stablefast3d, or triposr)',
        },
      });
    }

    const imagePath = req.file.path;
    const requested = (model || '').toLowerCase();

    // 'triposr' runs the real generative pipeline (run_triposr.py via the adapter);
    // every other model routes through the empirically-validated detection +
    // primitive/retrieval pipeline (the default product path).
    if (requested === 'triposr') {
      logger.info('GENERATE', 'Starting TripoSR generative pipeline', { imagePath });
      const t = await triposrAdapter.runTripoSR(imagePath, config.OUTPUT_DIR);
      const md = t.metadata || {};
      logger.info('GENERATE', 'TripoSR pipeline complete', {
        glbUrl: t.glbUrl, label: md.object_label,
        confidence: md.clip_confidence, faces: md.faces, glbSize: md.glbSize,
      });
      return res.json({
        success: true,
        model: 'triposr',
        requestedModel: requested,
        glb: t.glbUrl,
        glbPath: t.glbPath,
        detection: {
          coco_label: md.object_label,
          label: md.object_label,
          confidence: md.clip_confidence,
        },
        category: md.ifc_category,
        ifcClass: md.ifc_class,
        dimensions_m: md.estimated_dimensions_m,
        dimension_source: 'depth_anything_v2_metric',
        mesh_source: 'triposr',
        metadata: {
          method: md.method,
          faces: md.faces,
          glbSize: md.glbSize,
          device: md.device,
        },
      });
    }

    logger.info('GENERATE', `Starting detection pipeline (requested model: ${model})`, { imagePath });
    const result = await runDetectAndPlace(imagePath, config.OUTPUT_DIR);

    logger.info('GENERATE', 'detection pipeline complete', {
      glbUrl: result.glbUrl,
      category: result.category,
      ifcClass: result.ifc_class,
      confidence: result.detection?.confidence,
      glbSize: result.glb_size_bytes,
    });

    return res.json({
      success: true,
      model: 'detect-and-place',
      requestedModel: requested,
      glb: result.glbUrl,
      glbPath: result.glbPath,
      detection: result.detection,
      category: result.category,
      ifcClass: result.ifc_class,
      dimensions_m: result.dimensions_m,
      dimension_source: result.dimension_source,
      mesh_source: result.mesh_source,
      retrieval: result.retrieval,
      extra_meta: result.extra_meta,
      library_used: result.library_used,
      metadata: {
        method: result.method,
        faces: result.faces,
        glbSize: result.glb_size_bytes,
        latencyMs: result.latency_ms,
        device: result.device,
      },
    });

  } catch (error) {
    // Clean up uploaded file on error
    if (req.file) {
      try {
        fs.unlinkSync(req.file.path);
      } catch (e) {
        // Ignore cleanup errors
      }
    }

    logger.error('GENERATE', 'Generation error', { error: error.message });
    next(error);
  }
});

// ============================================================================
// GET /api/models/validate - Validate model availability
// ============================================================================

router.get('/models/validate', async (req, res, next) => {
  try {
    const validation = await Promise.all([
      instantMeshAdapter.validateInstantMesh(),
      stableFast3DAdapter.validateStableFast3D(),
      triposrAdapter.validateTripoSR(),
    ]);

    res.json({
      success: true,
      models: validation,
      allAvailable: validation.every(m => m.available),
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
