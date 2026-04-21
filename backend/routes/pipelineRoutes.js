/**
 * Pipeline Routes - Full Workflow - Phase 7
 * Handles POST /api/pipeline endpoint
 */

const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const router = express.Router();

const logger = require('../middleware/logger');
const config = require('../config/env');
const pipeline = require('../services/pipeline');

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
// GET /api/pipeline/info - Get pipeline information
// ============================================================================

router.get('/pipeline/info', (req, res) => {
  try {
    const pipelineInfo = pipeline.getPipelineInfo();
    
    res.json({
      success: true,
      pipeline: pipelineInfo,
    });
  } catch (error) {
    logger.error('PIPELINE', 'Failed to get info', { error: error.message });
    res.status(500).json({
      success: false,
      error: {
        code: 'INFO_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// POST /api/pipeline/run - Run complete pipeline
// ============================================================================

router.post('/pipeline/run', upload.single('image'), async (req, res, next) => {
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

    const { model, processMesh, exportIFC, objectName, position, rotation } = req.body;

    if (!model) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'MISSING_MODEL',
          message: 'Model selection required',
        },
      });
    }

    const imagePath = req.file.path;
    logger.info('PIPELINE', 'Starting full pipeline via API', {
      image: req.file.originalname,
      model: model,
    });

    const pipelineResult = await pipeline.runFullPipeline(imagePath, model, {
      outputDir: config.OUTPUT_DIR,
      processMesh: processMesh !== 'false',
      exportIFC: exportIFC !== 'false',
      objectName: objectName || `${model} Generated`,
      position: position ? JSON.parse(position) : [0, 0, 0],
      rotation: rotation ? JSON.parse(rotation) : [0, 0, 0],
    });

    // Clean up uploaded image
    try {
      fs.unlinkSync(imagePath);
    } catch (e) {
      logger.warn('PIPELINE', 'Failed to clean up uploaded image', { imagePath });
    }

    logger.info('PIPELINE', 'Pipeline completed successfully via API', {
      glbUrl: pipelineResult.output.glbUrl,
      ifcUrl: pipelineResult.output.ifcUrl,
      duration: pipelineResult.duration_ms,
    });

    return res.json(pipelineResult);

  } catch (error) {
    // Clean up uploaded file on error
    if (req.file) {
      try {
        fs.unlinkSync(req.file.path);
      } catch (e) {
        // Ignore cleanup errors
      }
    }

    logger.error('PIPELINE', 'Pipeline error', { error: error.message });
    next(error);
  }
});

module.exports = router;
