/**
 * API Routes - Generate 3D Models - Phase 3
 * Handles POST /api/generate endpoint
 */

const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const router = express.Router();

const logger = require('../middleware/logger');
const config = require('../config/env');

// Import AI model adapters
const instantMeshAdapter = require('../ai/instantMesh');
const stableFast3DAdapter = require('../ai/stablefast3d');
const triposrAdapter = require('../ai/triposr');

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
    logger.info('GENERATE', `Starting ${model} inference`, { imagePath });

    // Route to appropriate AI adapter
    let result;
    switch (model.toLowerCase()) {
      case 'instantmesh':
        result = await instantMeshAdapter.runInstantMesh(imagePath, config.OUTPUT_DIR);
        break;
      case 'stablefast3d':
        result = await stableFast3DAdapter.runStableFast3D(imagePath, config.OUTPUT_DIR);
        break;
      case 'triposr':
        result = await triposrAdapter.runTripoSR(imagePath, config.OUTPUT_DIR);
        break;
      default:
        return res.status(400).json({
          success: false,
          error: {
            code: 'INVALID_MODEL',
            message: `Unknown model: ${model}. Use: instantmesh, stablefast3d, or triposr`,
          },
        });
    }

    // Clean up uploaded image
    try {
      fs.unlinkSync(imagePath);
    } catch (e) {
      logger.warn('GENERATE', 'Failed to clean up uploaded image', { imagePath });
    }

    logger.info('GENERATE', `${model} inference complete`, {
      glbUrl: result.glbUrl,
      glbSize: result.metadata.glbSize,
    });

    return res.json({
      success: true,
      model: model.toLowerCase(),
      glb: result.glbUrl,
      glbPath: result.glbPath,
      metadata: result.metadata,
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
