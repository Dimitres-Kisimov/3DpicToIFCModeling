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

// Serve a small set of bundled sample images for the "Use sample" buttons.
// This lets users test the pipeline without ever invoking the OS file dialog.
app.use('/sample', express.static(path.join(__dirname, '../backend/triposr/examples')));

// Room-builder assets (merged from the retired Flask app on :8000):
// /out           -> scratch preview dir (scene.glb/scene.ifc/renders) — never cached,
//                   the same URL is refetched after every regenerate
// /thumb         -> ABO catalog thumbnails
// /api/generated -> persisted user-generated assets (GLB/IFC)
const noStore = { setHeaders: (res) => res.setHeader('Cache-Control', 'no-store, max-age=0') };
app.use('/out', express.static(path.resolve(process.cwd(), config.ROOM_OUT_DIR), noStore));
app.use('/thumb', express.static(path.join(__dirname, '../data/mesh_library_abo')));
app.use('/api/generated', express.static(path.join(__dirname, '../data/generated_assets')));

// Research artifacts: the cloud 5-model AI benchmark gallery (used to live on :8900)
// now rides on the ONE app — see /hub.html for the index of every comparison page.
app.use('/gallery', express.static(path.join(__dirname, '../deliverable/cloud_gallery')));

// Engine manuals (markdown sources) — rendered by /manuals.html
app.use('/manuals-src', express.static(path.join(__dirname, '../deliverable/manuals')));

// Benchmark galleries + candidate visualizer (used to live on :8000) — the 11
// list pages, the multi-AI 3D visualizer, and the photo-angle guide, one origin.
app.use('/benchmark', express.static(path.join(__dirname, '../benchmark')));
app.use('/docs-img', express.static(path.join(__dirname, '../docs')));   // showcase renders

// ============================================================================
// ROUTES
// ============================================================================

// Health check endpoint — includes the resource picture (queues, memory, workers)
app.get('/api/health', (req, res) => {
  let queues = {};
  try {
    queues = {
      gpu: require('./services/gpuQueue').stats(),
      cpu: require('./services/cpuQueue').stats(),
      detectWorker: require('./services/detectWorker').stats(),
    };
  } catch (e) { /* stats are best-effort */ }
  const mem = process.memoryUsage();
  res.json({
    success: true,
    message: 'Server is running',
    timestamp: new Date().toISOString(),
    uptime_s: Math.round(process.uptime()),
    memory_mb: { rss: Math.round(mem.rss / 1048576), heapUsed: Math.round(mem.heapUsed / 1048576) },
    queues,
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

// Room builder + building population (merged from the retired Flask app)
const roomRoutes = require('./routes/roomRoutes');
app.use('/api', roomRoutes);

const buildingRoutes = require('./routes/buildingRoutes');
app.use('/api', buildingRoutes);

// v4: procurement — cheapest visually-similar real product for a generated item
const procurementRoutes = require('./routes/procurementRoutes');
app.use('/api', procurementRoutes);

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
const directories = [config.TEMP_DIR, config.UPLOAD_DIR, config.OUTPUT_DIR, config.ROOM_OUT_DIR];
directories.forEach((dir) => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    logger.info('STARTUP', `Created directory: ${dir}`);
  }
});

// Room preview is ephemeral by design — start with a clean slate (as Flask did)
roomRoutes.clearScratch();

// Start server
// Bind to 0.0.0.0 so both IPv4 (127.0.0.1) and IPv6 (::1) work. Node's
// default resolution of "localhost" returns ::1 first on Windows, which
// blocks browsers that prefer IPv4.
const bindHost = (config.HOST === 'localhost' || !config.HOST) ? '0.0.0.0' : config.HOST;
const server = app.listen(config.PORT, bindHost, () => {
  logger.info('STARTUP', `Server running on http://${bindHost}:${config.PORT} (try http://localhost:${config.PORT})`);
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
