/**
 * buildingRoutes — populate REAL architectural IFCs, for ANY building the user adds.
 *
 *   GET  /api/buildings               -> registry (bundled samples + uploads), profiles
 *   POST /api/buildings/upload        -> add a building: sniff, probe, register, prepare
 *   GET  /api/building/:bid/rooms     -> rooms + storeys + smart suggestions
 *   POST /api/building/:bid/populate  -> per-room picks -> shell + movable pieces
 *   POST /api/building/:bid/save      -> merge dragged positions -> one GLB
 *
 * Scale posture: heavy building jobs run SERIALLY (each Python child can hold GBs
 * for a big IFC); geometry is cached per building (first scan pays, repeats are
 * solver-only); timeouts scale with the building's probed product count; every
 * building gets its own scratch dir so sessions never clobber each other.
 */
const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const multer = require('multer');
const config = require('../config/env');
const logger = require('../middleware/logger');
const roomApi = require('../services/roomApi');
const cpuQueue = require('../services/cpuQueue');
const { executePythonScript } = require('../services/pythonBridge');

const router = express.Router();
const REPO_ROOT = path.join(__dirname, '..', '..');
const ROOM_OUT = path.resolve(REPO_ROOT, config.ROOM_OUT_DIR);
const SAMPLES_DIR = path.join(REPO_ROOT, 'sample_buildings');
const BUILDINGS_DIR = path.join(REPO_ROOT, 'data', 'buildings');
const B_MANIFEST = path.join(BUILDINGS_DIR, 'manifest.json');
const MAX_BUILDINGS = 25;

// ---------------------------------------------------------------------------
// registry: bundled sample_buildings/*.ifc  ∪  uploaded data/buildings entries
// ---------------------------------------------------------------------------
function readManifest() {
  try { return JSON.parse(fs.readFileSync(B_MANIFEST, 'utf-8')); }
  catch (e) { return { buildings: [] }; }
}
function writeManifest(m) {
  fs.mkdirSync(BUILDINGS_DIR, { recursive: true });
  const tmp = B_MANIFEST + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(m, null, 1));
  fs.renameSync(tmp, B_MANIFEST);           // atomic under concurrent jobs
}

// All manifest mutations go through ONE promise chain with a fresh read inside
// the critical section — an upload handler and a prepare-completion callback
// interleaving a read-modify-write would otherwise clobber each other's status.
let _manifestLock = Promise.resolve();
function mutateManifest(fn) {
  const p = _manifestLock.then(() => {
    const m = readManifest();
    fn(m);
    writeManifest(m);
  });
  _manifestLock = p.catch(() => {});
  return p;
}
function registry() {
  const list = [];
  if (fs.existsSync(SAMPLES_DIR)) {
    for (const fn of fs.readdirSync(SAMPLES_DIR)) {
      if (!/\.ifc$/i.test(fn)) continue;
      const legacy = fn === 'Duplex_Architecture.ifc';
      list.push({
        id: legacy ? 'duplex'
          : 's_' + fn.replace(/\.ifc$/i, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 40),
        name: legacy ? 'Duplex Apartment' : fn.replace(/\.ifc$/i, '').replace(/[_-]+/g, ' '),
        ifc: path.join(SAMPLES_DIR, fn), bundled: true, status: 'ready', profile: null,
      });
    }
  }
  for (const b of (readManifest().buildings || [])) {
    list.push({ id: b.id, name: b.name, ifc: path.join(BUILDINGS_DIR, b.file),
                bundled: false, status: b.status || 'ready', profile: b.profile || null });
  }
  return list;
}
const building = (bid) => registry().find((b) => b.id === bid && fs.existsSync(b.ifc));

// per-building scratch — sessions for different buildings never clobber
const scratchDir = (bid) => path.join(ROOM_OUT, `bldg_${bid}`);

// timeouts scale with probed complexity (Duplex ≈ 300 products ≈ 1 min)
function populateTimeout(b) {
  const products = (b.profile && b.profile.products) || 600;
  return Math.min(1800000, 300000 + products * 600);
}
function roomsTimeout(b) {
  const products = (b.profile && b.profile.products) || 600;
  return Math.min(900000, 120000 + products * 300);
}

// heavy building jobs run one-at-a-time: each Python child may hold an entire
// parsed IFC + trimesh scene (GBs for large models) — two at once could swap-storm
let bTail = Promise.resolve();
function buildingQueue(fn, label) {
  const p = bTail.then(() => cpuQueue.run(fn, label));
  bTail = p.catch(() => {});
  return p;
}

// rooms responses cached per (id, file mtime+size) for the process lifetime
const _roomsCache = new Map();
const roomsKey = (b) => {
  const st = fs.statSync(b.ifc);
  return `${b.id}:${Math.round(st.mtimeMs)}:${st.size}`;
};

// ---------------------------------------------------------------------------
// routes
// ---------------------------------------------------------------------------
router.get('/buildings', (req, res) => {
  res.json(registry().map(({ id, name, bundled, status, profile }) => ({
    id, name, bundled, status,
    profile: profile ? {
      storeys: profile.storeys, spaces: profile.spaces, products: profile.products,
      size_mb: profile.size_mb, est_populate_min: profile.est_populate_min,
      warnings: profile.warnings || [],
    } : null,
  })));
});

// ---- add a building -----------------------------------------------------------
const bUpload = multer({
  storage: multer.diskStorage({
    destination: (req, file, cb) => {
      fs.mkdirSync(config.UPLOAD_DIR, { recursive: true });
      cb(null, config.UPLOAD_DIR);
    },
    filename: (req, file, cb) =>
      cb(null, `bldg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.ifc`),
  }),
  limits: { fileSize: 250 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ext === '.ifc') cb(null, true);
    else if (ext === '.ifczip' || ext === '.ifcxml') {
      cb(new Error('please export a plain .ifc (STEP) file — .ifczip/.ifcxml are not supported'));
    } else cb(new Error('only .ifc building files are accepted'));
  },
});

router.post('/buildings/upload', bUpload.single('file'), async (req, res, next) => {
  const drop = () => { try { fs.unlinkSync(req.file.path); } catch (e) {} };
  try {
    if (!req.file) return res.status(400).json({ ok: false, error: "no file (field 'file')" });
    // sniff the STEP header — don't trust the extension
    const head = Buffer.alloc(96);
    const fd = fs.openSync(req.file.path, 'r');
    fs.readSync(fd, head, 0, 96, 0);
    fs.closeSync(fd);
    if (!head.toString('utf-8').includes('ISO-10303-21')) {
      drop();
      return res.status(400).json({ ok: false, error: 'not an IFC (STEP) file' });
    }
    const man = readManifest();
    if ((man.buildings || []).length >= MAX_BUILDINGS) {
      drop();
      return res.status(400).json({ ok: false, error: `building limit reached (${MAX_BUILDINGS}) — remove one first` });
    }

    // probe: usable? how heavy? (size-scaled timeout; parsing IS the cost)
    const probeTimeout = Math.round(Math.min(900000, 120000 + req.file.size / 1024));
    const probe = await buildingQueue(
      () => roomApi.call('register_building', { path: req.file.path }, { timeout: probeTimeout }),
      'building-probe');
    if (probe.ok === false) {
      drop();
      const status = probe.status || 400;
      delete probe.status;
      return res.status(status).json(probe);
    }

    const uid = 'b_' + crypto.randomBytes(5).toString('hex');
    const stem = (req.file.originalname || 'building').replace(/\.ifc$/i, '')
      .replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 48) || 'building';
    const fileName = `${uid}__${stem}.ifc`;
    fs.mkdirSync(BUILDINGS_DIR, { recursive: true });
    fs.renameSync(req.file.path, path.join(BUILDINGS_DIR, fileName));

    const name = (probe.profile && probe.profile.name) || stem.replace(/[_-]+/g, ' ');
    await mutateManifest((m) => {
      m.buildings = m.buildings || [];
      m.buildings.push({ id: uid, name, file: fileName, status: 'preparing', profile: probe.profile });
    });
    logger.info('BUILDING', 'Registered building', { id: uid, name, profile: probe.profile });

    // background prepare: geometry cache + decimated shell — the user's first
    // populate then skips the expensive create_shape sweep entirely
    buildingQueue(
      () => roomApi.call('prepare_building', { path: path.join(BUILDINGS_DIR, fileName) },
                         { timeout: 1800000 }),
      `building-prepare:${uid}`)
      .then((r) => logger.info('BUILDING', 'Prepared', { id: uid, ok: r && r.ok }))
      .catch((e) => logger.warn('BUILDING', 'Prepare failed (populate will pay the cost)', { id: uid, error: e.message }))
      .finally(() => mutateManifest((m) => {
        const entry = (m.buildings || []).find((x) => x.id === uid);
        if (entry) entry.status = 'ready';
      }));

    res.json({ ok: true, building: { id: uid, name, status: 'preparing', profile: probe.profile } });
  } catch (err) { drop(); next(err); }
});

// ---- rooms ---------------------------------------------------------------------
router.get('/building/:bid/rooms', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });
    const key = roomsKey(b);
    if (_roomsCache.has(key)) return res.json(_roomsCache.get(key));

    const result = await buildingQueue(
      () => roomApi.call('building_rooms', { ifc: b.ifc }, { timeout: roomsTimeout(b) }),
      `building-rooms:${b.id}`);
    if (result.ok === false) {
      return res.status(result.status || 500).json({ error: result.error });
    }
    const payload = { rooms: result.rooms, categories: result.categories,
                      storeys: result.storeys || [] };
    _roomsCache.set(key, payload);
    res.json(payload);
  } catch (err) { next(err); }
});

// ---- populate ------------------------------------------------------------------
router.post('/building/:bid/populate', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });

    const picks = (req.body && req.body.picks) || {};
    const movDir = scratchDir(b.id);
    fs.rmSync(movDir, { recursive: true, force: true });
    fs.mkdirSync(movDir, { recursive: true });
    const picksPath = path.join(movDir, 'picks.json');   // per-building: no race
    fs.writeFileSync(picksPath, JSON.stringify(picks));

    const r = await buildingQueue(
      () => executePythonScript('populate_building.py', [
        b.ifc,
        path.join(movDir, '_ignore.glb'),
        '--picks', picksPath,
        '--movable', movDir,
      ], { timeout: populateTimeout(b) }),
      `building-populate:${b.id}`);
    const result = r.stdout && typeof r.stdout === 'object' ? r.stdout : null;
    if (!r.success || !result) {
      return res.status(500).json({ ok: false, error: `populate failed (exit ${r.exitCode})` });
    }
    const man = JSON.parse(fs.readFileSync(path.join(movDir, 'furniture.json'), 'utf-8'));
    const base = `/out/bldg_${b.id}`;
    const pieces = (man.pieces || []).map((p) => ({
      id: p.id, category: p.category, glb: `${base}/${p.glb}`, pos: p.pos,
      room: p.room, dims: p.dims || null,
    }));
    res.json({
      ok: true,
      shell: `${base}/shell.glb`,
      pieces,
      zones: man.zones || {},          // people-space halos per piece (world XY)
      placed: result.furniture_placed,
      rooms: result.rooms_populated,
      clashes: result.furniture_furniture_clashes,
      schedule: result.schedule || [],
    });
  } catch (err) { next(err); }
});

// ---- save ----------------------------------------------------------------------
router.post('/building/:bid/save', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });

    const positions = (req.body && req.body.positions) || {};
    const result = await cpuQueue.run(
      () => roomApi.call('building_save',
        { out_dir: ROOM_OUT, bldg_dir: scratchDir(b.id), positions }, { timeout: 300000 }),
      `building-save:${b.id}`);
    if (result.ok === false) {
      return res.status(result.status || 500).json(result);
    }
    res.json({ ok: true, glb: `/out/bldg_${b.id}/${result.glb_name || 'building_final.glb'}` });
  } catch (err) { next(err); }
});

module.exports = router;
