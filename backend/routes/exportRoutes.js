/**
 * Export Routes - IFC Export - Phase 6
 * Handles POST /api/export endpoints
 */

const express = require('express');
const router = express.Router();
const fs = require('fs');

const logger = require('../middleware/logger');
const ifcExporter = require('../services/ifcExporter');
const { spawn } = require('child_process');
const path = require('path');
let config = {}; try { config = require('../config'); } catch (e) {}

// Run the IFC optimizer (geometry decimation + instancing + precision rounding) on an exported IFC.
function runOptimizeIFC(inPath, outPath) {
  return new Promise((resolve) => {
    const script = path.join(__dirname, '..', 'python-scripts', 'optimize_ifc.py');
    // pin the interpreter that has ifcopenshell/trimesh/pymeshfix/fast_simplification
    const py = config.PYTHON_PATH
      || 'C:\\Users\\dimik\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe';
    const child = spawn(py, [script, inPath, outPath], { cwd: path.join(__dirname, '..', '..') });
    let out = '';
    child.stdout.on('data', (c) => { out += c.toString(); });
    child.on('error', () => resolve(null));
    child.on('close', () => {
      try { resolve(JSON.parse(out.trim().split('\n').pop())); } catch (e) { resolve(null); }
    });
  });
}

// ============================================================================
// GET /api/export/formats - Get available export formats
// ============================================================================

router.get('/export/formats', (req, res) => {
  try {
    const formats = ifcExporter.getAvailableFormats();
    
    res.json({
      success: true,
      formats: formats,
    });
  } catch (error) {
    logger.error('EXPORT', 'Failed to get formats', { error: error.message });
    res.status(500).json({
      success: false,
      error: {
        code: 'FORMATS_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// POST /api/export/ifc - Export scene to IFC
// ============================================================================

router.post('/export/ifc', async (req, res, next) => {
  try {
    const { objects, format } = req.body;

    if (!objects || !Array.isArray(objects)) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'INVALID_INPUT',
          message: 'objects array is required',
        },
      });
    }

    if (objects.length === 0) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'EMPTY_SCENE',
          message: 'No objects to export',
        },
      });
    }

    const exportFormat = format || 'ifc2x3';
    logger.info('EXPORT', `Exporting ${objects.length} objects to ${exportFormat}`);

    // For now, only support IFC2x3
    if (exportFormat !== 'ifc2x3') {
      return res.status(400).json({
        success: false,
        error: {
          code: 'FORMAT_NOT_SUPPORTED',
          message: `Format not supported: ${exportFormat}`,
        },
      });
    }

    // Validate that all objects have required GLB paths
    const validObjects = objects.filter(obj => {
      if (!obj.glbPath && !obj.glbUrl) {
        logger.warn('EXPORT', `Object missing GLB path: ${obj.id}`);
        return false;
      }
      return true;
    });

    if (validObjects.length === 0) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'NO_VALID_OBJECTS',
          message: 'No objects have valid GLB paths',
        },
      });
    }

    // Export to IFC
    const result = await ifcExporter.exportSceneToIFC(validObjects, './outputs');

    // Optimize the IFC (decimate + geometry-instance + precision-round) unless the client opts out
    let optimized = null;
    if (req.body.optimize !== false && result.ifcPath) {
      try {
        const optPath = result.ifcPath.replace(/\.ifc$/i, '_optimized.ifc');
        optimized = await runOptimizeIFC(result.ifcPath, optPath);
        if (optimized && optimized.ok) {
          result.ifcPath = optPath;
          result.ifcUrl = (result.ifcUrl || '').replace(/\.ifc$/i, '_optimized.ifc');
          result.metadata.optimized = optimized;
        }
      } catch (e) { logger.warn('EXPORT', 'IFC optimize skipped', { error: e.message }); }
    }

    logger.info('EXPORT', 'IFC export successful', {
      ifcUrl: result.ifcUrl,
      ifcSize: result.metadata.ifcSize,
      optimizedReductionPct: optimized ? optimized.size_reduction_pct : null,
    });

    return res.json({
      success: true,
      format: exportFormat,
      ifcUrl: result.ifcUrl,
      ifcPath: result.ifcPath,
      metadata: result.metadata,
      optimized,
    });

  } catch (error) {
    logger.error('EXPORT', 'IFC export error', { error: error.message });
    next(error);
  }
});

// ============================================================================
// POST /api/export/glb-to-ifc - Convert single GLB to IFC
// ============================================================================

router.post('/export/glb-to-ifc', async (req, res, next) => {
  try {
    const { glbPath, objectInfo } = req.body;

    if (!glbPath) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'MISSING_GLB_PATH',
          message: 'glbPath is required',
        },
      });
    }

    if (!fs.existsSync(glbPath)) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'GLB_NOT_FOUND',
          message: `GLB file not found: ${glbPath}`,
        },
      });
    }

    logger.info('EXPORT', 'Converting GLB to IFC', { glbPath });

    const result = await ifcExporter.exportGLBToIFC(glbPath, objectInfo || {}, './outputs');

    logger.info('EXPORT', 'GLB to IFC conversion successful', {
      ifcUrl: result.ifcUrl,
    });

    return res.json({
      success: true,
      ifcUrl: result.ifcUrl,
      ifcPath: result.ifcPath,
      metadata: result.metadata,
    });

  } catch (error) {
    logger.error('EXPORT', 'GLB to IFC conversion error', { error: error.message });
    next(error);
  }
});

// ============================================================================
// POST /api/export/xkt - Convert IFC → XKT (Sprint 3)
// ============================================================================

router.post('/export/xkt', async (req, res, next) => {
  try {
    const { ifcPath } = req.body;
    if (!ifcPath) {
      return res.status(400).json({ success: false, error: { code: 'MISSING_IFC', message: 'ifcPath required' } });
    }
    if (!fs.existsSync(ifcPath)) {
      return res.status(400).json({ success: false, error: { code: 'IFC_NOT_FOUND', message: `IFC not found: ${ifcPath}` } });
    }

    const { executePythonScript } = require('../services/pythonBridge');
    const path = require('path');
    const xktPath = ifcPath.replace(/\.ifc$/, '.xkt');

    logger.info('EXPORT', 'Converting IFC → XKT', { ifcPath, xktPath });
    const result = await executePythonScript('convert_to_xkt.py', [ifcPath, xktPath], { timeout: 120000 });

    if (!result.success || !fs.existsSync(xktPath)) {
      throw new Error(result.stderr || 'XKT conversion failed');
    }

    return res.json({
      success: true,
      xktPath,
      xktUrl: `/outputs/${path.basename(xktPath)}`,
      metadata: result.stdout?.data || {},
    });
  } catch (error) {
    logger.error('EXPORT', 'XKT conversion error', { error: error.message });
    next(error);
  }
});

// ============================================================================
// GET /api/export/list - List recent exports
// ============================================================================

router.get('/export/list', (req, res) => {
  try {
    const outputDir = './outputs';
    
    if (!fs.existsSync(outputDir)) {
      return res.json({
        success: true,
        exports: [],
      });
    }

    const files = fs.readdirSync(outputDir)
      .filter(file => file.endsWith('.ifc'))
      .map(file => {
        const filepath = `${outputDir}/${file}`;
        const stats = fs.statSync(filepath);
        return {
          filename: file,
          url: `/outputs/${file}`,
          size: stats.size,
          created: stats.birthtime.toISOString(),
          modified: stats.mtime.toISOString(),
        };
      })
      .sort((a, b) => new Date(b.created) - new Date(a.created))
      .slice(0, 50); // Last 50 exports

    res.json({
      success: true,
      count: files.length,
      exports: files,
    });
  } catch (error) {
    logger.error('EXPORT', 'Failed to list exports', { error: error.message });
    res.status(500).json({
      success: false,
      error: {
        code: 'LIST_ERROR',
        message: error.message,
      },
    });
  }
});

module.exports = router;
