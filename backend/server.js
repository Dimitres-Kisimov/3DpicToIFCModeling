const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const config = require('./config/env');
const logger = require('./middleware/logger');
const errorHandler = require('./middleware/errorHandler');

const app = express();

// ============================================================================
// MIDDLEWARE
// ============================================================================

// CORS
app.use(cors({
  origin: ['http://localhost:3000', 'http://localhost:5000', 'http://127.0.0.1:3000'],
  credentials: true,
}));

// Body parser
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

// Request logging
app.use((req, res, next) => {
  logger.info('REQUEST', `${req.method} ${req.path}`);
  next();
});

// ============================================================================
// STATIC FILES
// ============================================================================

// Serve frontend
app.use(express.static(path.join(__dirname, '../frontend')));

// Serve outputs (generated files)
app.use('/outputs', express.static(path.join(__dirname, '../outputs')));

// Serve xeokit-sdk from local node_modules (avoids CDN dependency)
app.use('/vendor/xeokit-sdk', express.static(path.join(__dirname, '../node_modules/@xeokit/xeokit-sdk/dist')));

// ============================================================================
// ROUTES
// ============================================================================

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({
    success: true,
    message: 'Server is running',
    timestamp: new Date().toISOString(),
  });
});

// Health check with environment info
app.get('/api/debug/health', async (req, res, next) => {
  try {
    const { testEnvironment } = require('./services/pythonBridge');
    const envTest = await testEnvironment();

    res.json({
      success: true,
      server: {
        port: config.PORT,
        nodeEnv: config.NODE_ENV,
        uptime: process.uptime(),
      },
      python: envTest,
    });
  } catch (error) {
    next(error);
  }
});

// List available models
app.get('/api/models/available', (req, res) => {
  res.json({
    success: true,
    models: [
      {
        name: 'instantmesh',
        displayName: 'InstantMesh',
        description: 'Fast 3D mesh generation from single image',
      },
      {
        name: 'stablefast3d',
        displayName: 'StableFast3D',
        description: 'Stable and fast 3D model generation',
      },
      {
        name: 'triposr',
        displayName: 'TripoSR',
        description: 'High-quality 3D synthesis from images',
      },
    ],
  });
});

// Import and use API routes (Phase 3)
const apiRoutes = require('./routes/apiRoutes');
app.use('/api', apiRoutes);

// Import and use object routes (Phase 5)
const objectRoutes = require('./routes/objectRoutes');
app.use('/api', objectRoutes);

// Import and use export routes (Phase 6)
const exportRoutes = require('./routes/exportRoutes');
app.use('/api', exportRoutes);

// Import and use pipeline routes (Phase 7)
const pipelineRoutes = require('./routes/pipelineRoutes');
app.use('/api', pipelineRoutes);

// Import and use debug routes (Phase 8)
const debugRoutes = require('./routes/debugRoutes');
app.use('/api', debugRoutes);

// ============================================================================
// 404 HANDLER
// ============================================================================

app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: {
      code: 'NOT_FOUND',
      message: `Route not found: ${req.method} ${req.path}`,
    },
  });
});

// ============================================================================
// ERROR HANDLER
// ============================================================================

app.use(errorHandler);

// ============================================================================
// STARTUP
// ============================================================================

// Create necessary directories
const directories = [config.TEMP_DIR, config.UPLOAD_DIR, config.OUTPUT_DIR];
directories.forEach((dir) => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    logger.info('STARTUP', `Created directory: ${dir}`);
  }
});

// Start server
const server = app.listen(config.PORT, config.HOST, () => {
  logger.info('STARTUP', `Server running on http://${config.HOST}:${config.PORT}`);
  logger.info('STARTUP', `Environment: ${config.NODE_ENV}`);
  logger.info('STARTUP', `GPU enabled: ${config.USE_GPU}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('SHUTDOWN', 'SIGTERM received, closing server');
  server.close(() => {
    logger.info('SHUTDOWN', 'Server closed');
    process.exit(0);
  });
});

module.exports = app;
