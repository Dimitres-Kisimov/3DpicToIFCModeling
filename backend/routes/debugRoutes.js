/**
 * Debug Routes - Diagnostics and Performance Monitoring - Phase 8
 * Provides endpoints for testing, profiling, and debugging
 */

const express = require('express');
const router = express.Router();
const fs = require('fs');
const os = require('os');

const logger = require('../middleware/logger');
const config = require('../config/env');

// ============================================================================
// System Info
// ============================================================================

router.get('/debug/system', (req, res) => {
  try {
    const systemInfo = {
      platform: os.platform(),
      arch: os.arch(),
      cpus: os.cpus().length,
      memory: {
        total: os.totalmem(),
        free: os.freemem(),
        used: os.totalmem() - os.freemem(),
      },
      uptime: os.uptime(),
      loadAverage: os.loadavg(),
    };

    res.json({
      success: true,
      system: systemInfo,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

// ============================================================================
// File System Status
// ============================================================================

router.get('/debug/storage', (req, res) => {
  try {
    const dirs = {
      uploads: fs.existsSync(config.UPLOAD_DIR) ? 
        fs.readdirSync(config.UPLOAD_DIR).length : 0,
      outputs: fs.existsSync(config.OUTPUT_DIR) ? 
        fs.readdirSync(config.OUTPUT_DIR).length : 0,
      temp: fs.existsSync(config.TEMP_DIR) ? 
        fs.readdirSync(config.TEMP_DIR).length : 0,
    };

    const storage = {
      directories: {
        uploads: {
          path: config.UPLOAD_DIR,
          files: dirs.uploads,
        },
        outputs: {
          path: config.OUTPUT_DIR,
          files: dirs.outputs,
        },
        temp: {
          path: config.TEMP_DIR,
          files: dirs.temp,
        },
      },
      diskFree: require('child_process')
        .execSync('df /').toString().split('\n')[1].split(/\s+/)[3],
    };

    res.json({
      success: true,
      storage: storage,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

// ============================================================================
// Request Statistics
// ============================================================================

let requestStats = {
  total: 0,
  byMethod: {},
  byPath: {},
  errors: 0,
  startTime: Date.now(),
};

// Middleware to track requests
router.use((req, res, next) => {
  requestStats.total++;
  requestStats.byMethod[req.method] = (requestStats.byMethod[req.method] || 0) + 1;
  requestStats.byPath[req.path] = (requestStats.byPath[req.path] || 0) + 1;

  const originalSend = res.send;
  res.send = function(data) {
    if (res.statusCode >= 400) {
      requestStats.errors++;
    }
    return originalSend.call(this, data);
  };

  next();
});

router.get('/debug/stats', (req, res) => {
  try {
    const uptime = (Date.now() - requestStats.startTime) / 1000;
    
    res.json({
      success: true,
      statistics: {
        uptime_seconds: uptime.toFixed(2),
        total_requests: requestStats.total,
        average_per_second: (requestStats.total / uptime).toFixed(2),
        by_method: requestStats.byMethod,
        by_path: requestStats.byPath,
        errors: requestStats.errors,
        error_rate: ((requestStats.errors / requestStats.total) * 100).toFixed(2) + '%',
      },
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

// ============================================================================
// Configuration Dump (with sensitive data hidden)
// ============================================================================

router.get('/debug/config', (req, res) => {
  try {
    const safeConfig = {
      PORT: config.PORT,
      HOST: config.HOST,
      NODE_ENV: config.NODE_ENV,
      USE_GPU: config.USE_GPU,
      CUDA_VISIBLE_DEVICES: config.CUDA_VISIBLE_DEVICES,
      MAX_FILE_SIZE: config.MAX_FILE_SIZE,
      LOG_LEVEL: config.LOG_LEVEL,
      PYTHON_PATH: 'configured',
      directories: {
        UPLOAD_DIR: config.UPLOAD_DIR,
        OUTPUT_DIR: config.OUTPUT_DIR,
        TEMP_DIR: config.TEMP_DIR,
        PYTHON_SCRIPTS_DIR: config.PYTHON_SCRIPTS_DIR,
      },
    };

    res.json({
      success: true,
      config: safeConfig,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

// ============================================================================
// Health Check with Full Details
// ============================================================================

router.get('/debug/health/full', async (req, res, next) => {
  try {
    const { testEnvironment } = require('../services/pythonBridge');
    const pipeline = require('../services/pipeline');

    const pythonEnv = await testEnvironment();
    const pipelineInfo = pipeline.getPipelineInfo();

    res.json({
      success: true,
      timestamp: new Date().toISOString(),
      server: {
        status: 'operational',
        uptime: process.uptime(),
        memory: process.memoryUsage(),
      },
      python: pythonEnv,
      pipeline: pipelineInfo,
      system: {
        platform: os.platform(),
        cpus: os.cpus().length,
        freeMemory: os.freemem(),
      },
    });
  } catch (error) {
    next(error);
  }
});

// ============================================================================
// Test Image Generation (for testing)
// ============================================================================

router.post('/debug/test/generate-image', (req, res) => {
  try {
    const size = req.body.size || 256;
    const format = req.body.format || 'png';

    // Create a simple test image (gradient)
    const canvas = require('canvas');
    if (!canvas) {
      return res.status(503).json({
        success: false,
        error: { message: 'Canvas library not available. Install with: npm install canvas' },
      });
    }

    const c = canvas.createCanvas(size, size);
    const ctx = c.getContext('2d');

    // Draw gradient
    const gradient = ctx.createLinearGradient(0, 0, size, size);
    gradient.addColorStop(0, 'red');
    gradient.addColorStop(0.5, 'yellow');
    gradient.addColorStop(1, 'blue');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);

    res.type(`image/${format}`);
    res.send(c.toBuffer(`image/${format}`));
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

// ============================================================================
// Memory Profiling
// ============================================================================

router.get('/debug/memory', (req, res) => {
  try {
    const memUsage = process.memoryUsage();
    
    res.json({
      success: true,
      memory: {
        rss: `${(memUsage.rss / 1024 / 1024).toFixed(2)} MB`,
        heapTotal: `${(memUsage.heapTotal / 1024 / 1024).toFixed(2)} MB`,
        heapUsed: `${(memUsage.heapUsed / 1024 / 1024).toFixed(2)} MB`,
        external: `${(memUsage.external / 1024 / 1024).toFixed(2)} MB`,
        arrayBuffers: `${(memUsage.arrayBuffers / 1024 / 1024).toFixed(2)} MB`,
      },
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: { message: error.message },
    });
  }
});

module.exports = router;
