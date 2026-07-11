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
const bigEngine = require('../ai/bigEngine');   // TripoSG/TRELLIS.2/SAM3D — VRAM-gated
const gpuQueue = require('../services/gpuQueue');   // serialize GPU jobs — never two on the 6 GB card
const roomApi = require('../services/roomApi');
const detectWorker = require('../services/detectWorker');
const crypto = require('crypto');

// D — image-hash result cache: the same photo detected twice costs zero seconds.
// Bounded, in-memory; entries whose GLB no longer exists on disk are dropped.
const _detectCache = new Map();     // md5(image) -> pipeline result
const _DETECT_CACHE_MAX = 100;

function detectCacheGet(hash) {
  const hit = _detectCache.get(hash);
  if (!hit) return null;
  if (!hit.glbPath || !fs.existsSync(hit.glbPath)) { _detectCache.delete(hash); return null; }
  return hit;
}
function detectCachePut(hash, result) {
  if (_detectCache.size >= _DETECT_CACHE_MAX) {
    _detectCache.delete(_detectCache.keys().next().value);   // evict oldest
  }
  _detectCache.set(hash, result);
}

// B3 — close the generator→room loop: every successfully generated object is
// registered into the room builder's catalog (data/generated_assets) so it is
// immediately pickable in "Build a room" with an OURS badge. Fire-and-forget:
// never delays the generation response; keep_source leaves the GLB in /outputs
// for the viewer.
function autoRegisterGenerated(glbPath, category, engine) {
  if (!glbPath) return;
  roomApi.call('register_upload', {
    path: glbPath,
    orig_name: `${category || 'object'}.glb`,
    category: category || undefined,
    engine: engine || undefined,     // picker badge shows which AI made it
    keep_source: true,
  }, { timeout: 120000 })
    .then((r) => {
      if (r && r.ok) {
        roomApi.invalidateCatalog(r.item && r.item.category);
        logger.info('GENERATE', 'Auto-registered into room catalog', r.item);
      } else {
        logger.warn('GENERATE', 'Auto-register skipped', { error: r && r.error });
      }
    })
    .catch((e) => logger.warn('GENERATE', 'Auto-register failed', { error: e.message }));
}

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
      // "Fast — from catalog" must actually USE the catalog: force retrieval (threshold 0) so it
      // never silently falls back to a slow TripoSR generation. Overridable via the env var.
      env: {
        ...process.env,
        SCS_TRIPOSR_SKIP_POSTPROC: '1',
        SCS_TRIPOSR_MIRROR: '0',
        SCS_RETRIEVAL_THRESHOLD: process.env.SCS_RETRIEVAL_THRESHOLD || '0',
      },
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
// GET /api/engines — the engine registry with availability for THIS machine.
// The frontend builds its selector from this; unavailable entries carry a
// plain-language reason ("Needs a 24 GB graphics card — you have 6 GB").
// ============================================================================

router.get('/engines', async (req, res) => {
  try {
    res.json({ success: true, engines: await bigEngine.listEngines() });
  } catch (e) {
    res.status(500).json({ success: false, error: { message: e.message } });
  }
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
      const forceGraft = /^(1|true|on|yes)$/i.test(String(req.body.graftBase || ''));
      logger.info('GENERATE', 'Starting TripoSR generative pipeline', { imagePath, forceGraft });
      // serialize on the GPU queue so concurrent requests can't OOM the 6 GB card
      const t = await gpuQueue.run(
        () => triposrAdapter.runTripoSR(imagePath, config.OUTPUT_DIR, { forceGraft }), 'triposr');
      const md = t.metadata || {};
      logger.info('GENERATE', 'TripoSR pipeline complete', {
        glbUrl: t.glbUrl, label: md.object_label,
        confidence: md.clip_confidence, faces: md.faces, glbSize: md.glbSize,
      });
      autoRegisterGenerated(t.glbPath, md.ifc_category, 'TSR');   // B3: appears in the room picker
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

    // Big external engines (TripoSG / TRELLIS.2 / SAM 3D) — only reachable when
    // /api/engines reported them available (VRAM + installed engines pack).
    const bigSpec = bigEngine.getEngine(requested);
    if (bigSpec && !bigSpec.builtin) {
      const engines = await bigEngine.listEngines();
      const st = engines.find((e) => e.id === requested);
      if (!st || !st.available) {
        return res.status(409).json({
          success: false,
          error: { code: 'ENGINE_UNAVAILABLE', message: (st && st.reason) || 'engine not available on this machine' },
        });
      }
      logger.info('GENERATE', `Starting big-engine pipeline: ${requested}`, { imagePath });
      const g = await gpuQueue.run(
        () => bigEngine.runBigEngine(requested, imagePath, config.OUTPUT_DIR), requested);
      autoRegisterGenerated(g.glbPath, undefined, g.engine);   // badge = which AI made it
      return res.json({
        success: true,
        model: requested,
        requestedModel: requested,
        glb: g.glbUrl,
        glbPath: g.glbPath,
        mesh_source: requested,
        metadata: { engine: g.engine, faces: g.faces },
      });
    }

    logger.info('GENERATE', `Starting detection pipeline (requested model: ${model})`, { imagePath });
    // D — same photo again? serve the cached result instantly
    const imageHash = crypto.createHash('md5').update(fs.readFileSync(imagePath)).digest('hex');
    let result = detectCacheGet(imageHash);
    if (result) {
      logger.info('GENERATE', 'detect cache hit', { hash: imageHash });
    } else {
      // D — warm worker first (models stay loaded, CPU-only: no GPU queue needed);
      // if the worker is broken, fall back to the old spawn-per-request GPU path.
      const outputName = `mesh_${Date.now()}.glb`;
      const outputGlb = path.join(config.OUTPUT_DIR, outputName);
      try {
        result = await detectWorker.run(imagePath, outputGlb);
        result.glbUrl = `/outputs/${outputName}`;
        result.glbPath = result.output_path || outputGlb;
      } catch (workerErr) {
        logger.warn('GENERATE', 'warm worker failed — cold fallback', { error: workerErr.message });
        result = await gpuQueue.run(() => runDetectAndPlace(imagePath, config.OUTPUT_DIR), 'detect');
      }
      detectCachePut(imageHash, result);
    }

    logger.info('GENERATE', 'detection pipeline complete', {
      glbUrl: result.glbUrl,
      category: result.category,
      ifcClass: result.ifc_class,
      confidence: result.detection?.confidence,
      glbSize: result.glb_size_bytes,
    });
    autoRegisterGenerated(result.glbPath, result.category,
      result.mesh_source === 'retrieval' ? 'CAT'
        : result.mesh_source === 'primitive' ? 'PRIM' : 'CAT');   // B3: appears in the room picker

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
