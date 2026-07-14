/**
 * roomRoutes — the room-builder API, ported 1:1 from the retired Flask app
 * (backend/app_server.py) onto the Node front door.
 *
 *   GET  /api/room/catalog          -> pickable categories (ABO + generated counts)
 *   GET  /api/room/items/:category  -> per-category mesh list for the picker
 *   POST /api/room/layout           -> {room, items, obstacles?, doors?} -> scene + IFC + renders
 *   POST /api/room/demo             -> one-click canned demo run (presentation-safe)
 *   POST /api/room/upload           -> register a user .glb/.ifc into the catalog
 *   POST /api/room/reset            -> wipe the scratch preview dir
 *
 * All Python work goes through room_api.py (see services/roomApi.js). Heavy jobs
 * run inside cpuQueue so bursts can't pile up solver/mesh processes.
 * Outputs land in the scratch dir served at /out (same URLs the Flask app used).
 */
const express = require('express');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const config = require('../config/env');
const logger = require('../middleware/logger');
const roomApi = require('../services/roomApi');
const cpuQueue = require('../services/cpuQueue');

const router = express.Router();
const REPO_ROOT = path.join(__dirname, '..', '..');
const ROOM_OUT = path.resolve(REPO_ROOT, config.ROOM_OUT_DIR);

// ---------------------------------------------------------------------------
// scratch helpers — the preview dir is ephemeral by design (nothing persists
// until the user exports); wiped on reset and at server startup (server.js)
// ---------------------------------------------------------------------------
function clearScratch() {
  if (!fs.existsSync(ROOM_OUT)) return;
  for (const entry of fs.readdirSync(ROOM_OUT)) {
    try {
      fs.rmSync(path.join(ROOM_OUT, entry), { recursive: true, force: true });
    } catch (_) { /* best-effort, like the Flask version */ }
  }
}

// send a room_api result: honour its ok/status, mirror Flask's status codes
function send(res, result) {
  if (result.ok === false) {
    const status = result.status || 500;
    delete result.status;
    return res.status(status).json(result);
  }
  return res.json(result);
}

// ---------------------------------------------------------------------------
// catalog browsing (cached in roomApi — no Python spawn after first load)
// ---------------------------------------------------------------------------
router.get('/room/catalog', async (req, res, next) => {
  try {
    res.json(await roomApi.getCatalog());          // bare array, same as Flask
  } catch (err) { next(err); }
});

router.get('/room/items/:category', async (req, res, next) => {
  try {
    res.json(await roomApi.getItems(req.params.category));
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// room layout — the core "select what you want, we place it or say it doesn't fit"
// ---------------------------------------------------------------------------
router.post('/room/layout', async (req, res, next) => {
  try {
    const body = req.body || {};
    const result = await cpuQueue.run(
      () => roomApi.call('layout', {
        room: body.room || {},
        items: body.items || [],
        obstacles: body.obstacles,
        doors: body.doors,
        out_dir: ROOM_OUT,
      }, { timeout: 300000 }),
      'room-layout'
    );
    send(res, result);
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// manual 2D-editor edits: move/rotate items -> re-validate -> schedule + IFC
// (rebuild=true also re-assembles scene.glb so exports match the manual truth)
// ---------------------------------------------------------------------------
router.post('/room/positions', async (req, res, next) => {
  try {
    const body = req.body || {};
    const result = await cpuQueue.run(
      () => roomApi.call('update_positions', {
        out_dir: ROOM_OUT,
        positions: body.positions || {},
        rebuild: !!body.rebuild,
      }, { timeout: 180000 }),
      'room-positions'
    );
    send(res, result);
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// demo run — the canned presentation scene, one click, no terminal
// ---------------------------------------------------------------------------
router.post('/room/demo', async (req, res, next) => {
  try {
    // default: the curated demo through the real pipeline; an explicit ?spec
    // may name a bundled legacy spec file (demo button, not a file API)
    const args = { out_dir: ROOM_OUT };
    if (req.body && req.body.spec) {
      args.spec_path = path.join(REPO_ROOT, 'demo', path.basename(req.body.spec));
    }
    const result = await cpuQueue.run(
      () => roomApi.call('demo_run', args, { timeout: 300000 }),
      'demo-run'
    );
    send(res, result);
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// user-generated asset upload -> categorize -> register in the room catalog
// ---------------------------------------------------------------------------
const upload = multer({
  storage: multer.diskStorage({
    destination: (req, file, cb) => {
      fs.mkdirSync(config.UPLOAD_DIR, { recursive: true });
      cb(null, config.UPLOAD_DIR);
    },
    filename: (req, file, cb) => {
      const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      cb(null, `roomasset-${suffix}${path.extname(file.originalname).toLowerCase()}`);
    },
  }),
  limits: { fileSize: config.MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ext === '.glb' || ext === '.ifc') cb(null, true);
    else cb(new Error('only .glb or .ifc accepted'));
  },
});

router.post('/room/upload', upload.single('file'), async (req, res, next) => {
  try {
    if (!req.file) {
      return res.status(400).json({ ok: false, error: "no file (field 'file')" });
    }
    const result = await roomApi.call('register_upload', {
      path: req.file.path,
      orig_name: req.file.originalname,
      category: req.body && req.body.category,
    }, { timeout: 120000 });
    if (result.ok) {
      roomApi.invalidateCatalog(result.item && result.item.category);
      logger.info('ROOM', 'Registered user asset', result.item);
    }
    send(res, result);
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// upload one or MANY furniture IFC files into a user-declared category —
// each becomes a colored GLB catalog item numbered <category>-USER-NNN
router.post('/room/catalog/custom', upload.array('files', 20), async (req, res, next) => {
  try {
    const category = String((req.body && req.body.category) || '').trim();
    if (!category) return res.status(400).json({ ok: false, error: 'category name required' });
    if (!req.files || !req.files.length) {
      return res.status(400).json({ ok: false, error: 'at least one .ifc file required' });
    }
    const results = [];
    for (const file of req.files) {
      // roomApi.call returns the command's JSON directly (same as every route here)
      const r = await roomApi.call('register_ifc_item',
        { path: file.path, category }, { timeout: 300000 });
      results.push({ file: file.originalname, ok: !!r.ok,
                     item: r.item || null, error: r.error || null });
      try { fs.unlinkSync(file.path); } catch (e) {}
    }
    roomApi.invalidateCatalog();
    res.json({ ok: results.some((r) => r.ok), category, results });
  } catch (err) { next(err); }
});

// delete a user-generated (OURS) item — files + manifest entry
// ---------------------------------------------------------------------------
router.delete('/room/generated/:gid', async (req, res, next) => {
  try {
    const result = await roomApi.call('delete_generated', { id: req.params.gid },
                                      { timeout: 30000 });
    if (result.ok) {
      roomApi.invalidateCatalog(result.category);
      logger.info('ROOM', 'Deleted generated asset', { id: req.params.gid });
    }
    send(res, result);
  } catch (err) { next(err); }
});

// ---------------------------------------------------------------------------
// reset — discard the current preview, start clean
// ---------------------------------------------------------------------------
router.post('/room/reset', (req, res) => {
  clearScratch();
  res.json({ ok: true });
});

module.exports = router;
module.exports.clearScratch = clearScratch;
module.exports.ROOM_OUT = ROOM_OUT;
