/**
 * Object Routes - Object Manipulation - Phase 5
 * Handles GET/PUT /api/objects endpoints
 */

const express = require('express');
const router = express.Router();

const logger = require('../middleware/logger');

// In-memory object store (in production, would use database)
const sceneObjects = new Map();

// ============================================================================
// GET /api/objects - Get all objects in scene
// ============================================================================

router.get('/objects', (req, res) => {
  try {
    const objects = Array.from(sceneObjects.values());
    
    logger.info('OBJECTS', `Retrieved ${objects.length} objects`);

    res.json({
      success: true,
      count: objects.length,
      objects: objects,
    });
  } catch (error) {
    logger.error('OBJECTS', 'Failed to retrieve objects', { error: error.message });
    res.status(500).json({
      success: false,
      error: {
        code: 'RETRIEVAL_ERROR',
        message: 'Failed to retrieve objects',
      },
    });
  }
});

// ============================================================================
// GET /api/objects/:id - Get specific object
// ============================================================================

router.get('/objects/:id', (req, res) => {
  try {
    const { id } = req.params;
    const object = sceneObjects.get(id);

    if (!object) {
      return res.status(404).json({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: `Object not found: ${id}`,
        },
      });
    }

    res.json({
      success: true,
      object: object,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'RETRIEVAL_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// POST /api/objects - Create/add new object
// ============================================================================

router.post('/objects', (req, res) => {
  try {
    const { id, name, glbUrl, position, rotation, scale, metadata } = req.body;

    if (!id || !glbUrl) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'MISSING_FIELDS',
          message: 'id and glbUrl are required',
        },
      });
    }

    if (sceneObjects.has(id)) {
      return res.status(409).json({
        success: false,
        error: {
          code: 'OBJECT_EXISTS',
          message: `Object already exists: ${id}`,
        },
      });
    }

    const object = {
      id,
      name: name || `Object ${id}`,
      glbUrl,
      position: position || [0, 0, 0],
      rotation: rotation || [0, 0, 0],
      scale: scale || [1, 1, 1],
      metadata: metadata || {},
      createdAt: new Date().toISOString(),
    };

    sceneObjects.set(id, object);
    logger.info('OBJECTS', `Created object: ${id}`);

    res.status(201).json({
      success: true,
      object: object,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'CREATION_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// PUT /api/objects/:id - Update object transform
// ============================================================================

router.put('/objects/:id', (req, res) => {
  try {
    const { id } = req.params;
    const { position, rotation, scale, metadata } = req.body;

    const object = sceneObjects.get(id);
    if (!object) {
      return res.status(404).json({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: `Object not found: ${id}`,
        },
      });
    }

    // Update fields
    if (position) object.position = position;
    if (rotation) object.rotation = rotation;
    if (scale) object.scale = scale;
    if (metadata) object.metadata = { ...object.metadata, ...metadata };

    object.updatedAt = new Date().toISOString();
    sceneObjects.set(id, object);

    logger.info('OBJECTS', `Updated object: ${id}`, { position, rotation, scale });

    res.json({
      success: true,
      object: object,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'UPDATE_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// DELETE /api/objects/:id - Remove object
// ============================================================================

router.delete('/objects/:id', (req, res) => {
  try {
    const { id } = req.params;

    if (!sceneObjects.has(id)) {
      return res.status(404).json({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: `Object not found: ${id}`,
        },
      });
    }

    sceneObjects.delete(id);
    logger.info('OBJECTS', `Deleted object: ${id}`);

    res.json({
      success: true,
      message: `Object deleted: ${id}`,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'DELETION_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// POST /api/objects/batch/clear - Clear all objects
// ============================================================================

router.post('/objects/batch/clear', (req, res) => {
  try {
    const count = sceneObjects.size;
    sceneObjects.clear();
    logger.info('OBJECTS', `Cleared ${count} objects from scene`);

    res.json({
      success: true,
      message: `Cleared ${count} objects`,
      count: count,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'CLEAR_ERROR',
        message: error.message,
      },
    });
  }
});

// ============================================================================
// POST /api/objects/batch/update - Batch update objects
// ============================================================================

router.post('/objects/batch/update', (req, res) => {
  try {
    const { updates } = req.body; // Array of { id, position, rotation, scale }

    if (!Array.isArray(updates)) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'INVALID_FORMAT',
          message: 'updates must be an array',
        },
      });
    }

    const results = [];
    for (const update of updates) {
      const object = sceneObjects.get(update.id);
      if (object) {
        if (update.position) object.position = update.position;
        if (update.rotation) object.rotation = update.rotation;
        if (update.scale) object.scale = update.scale;
        object.updatedAt = new Date().toISOString();
        results.push({ id: update.id, success: true });
      } else {
        results.push({ id: update.id, success: false, error: 'not found' });
      }
    }

    logger.info('OBJECTS', `Batch updated ${results.filter(r => r.success).length} objects`);

    res.json({
      success: true,
      updated: results.filter(r => r.success).length,
      failed: results.filter(r => !r.success).length,
      results: results,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        code: 'BATCH_ERROR',
        message: error.message,
      },
    });
  }
});

module.exports = router;
