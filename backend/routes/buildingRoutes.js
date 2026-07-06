/**
 * buildingRoutes — populate a REAL architectural IFC (loaded building), ported 1:1
 * from the retired Flask app (backend/app_server.py).
 *
 *   GET  /api/buildings               -> available buildings
 *   GET  /api/building/:bid/rooms     -> furnishable rooms + smart suggestions
 *   POST /api/building/:bid/populate  -> per-room picks -> shell.glb + movable pieces
 *   POST /api/building/:bid/save      -> merge dragged positions -> building_final.glb
 *
 * populate_building.py already has a clean CLI (it was subprocess-driven even under
 * Flask) so it is spawned directly; rooms/save go through the room_api dispatcher.
 */
const express = require('express');
const path = require('path');
const fs = require('fs');
const config = require('../config/env');
const roomApi = require('../services/roomApi');
const cpuQueue = require('../services/cpuQueue');
const { executePythonScript } = require('../services/pythonBridge');

const router = express.Router();
const REPO_ROOT = path.join(__dirname, '..', '..');
const ROOM_OUT = path.resolve(REPO_ROOT, config.ROOM_OUT_DIR);

const BUILDINGS = [{
  id: 'duplex',
  name: 'Duplex Apartment',
  ifc: path.join(REPO_ROOT, 'sample_buildings', 'Duplex_Architecture.ifc'),
}];

const building = (bid) => BUILDINGS.find((b) => b.id === bid);

// rooms listing parses the IFC + measures every space (~seconds) and the building
// files never change at runtime — cache per building for the life of the process
const _roomsCache = new Map();

router.get('/buildings', (req, res) => {
  res.json(BUILDINGS.map(({ id, name }) => ({ id, name })));
});

router.get('/building/:bid/rooms', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });
    if (_roomsCache.has(b.id)) return res.json(_roomsCache.get(b.id));

    const result = await cpuQueue.run(
      () => roomApi.call('building_rooms', { ifc: b.ifc }, { timeout: 120000 }),
      `building-rooms:${b.id}`
    );
    if (result.ok === false) {
      return res.status(result.status || 500).json({ error: result.error });
    }
    const payload = { rooms: result.rooms, categories: result.categories };
    _roomsCache.set(b.id, payload);
    res.json(payload);
  } catch (err) { next(err); }
});

router.post('/building/:bid/populate', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });

    const picks = (req.body && req.body.picks) || {};
    fs.mkdirSync(ROOM_OUT, { recursive: true });
    const picksPath = path.join(ROOM_OUT, 'building_picks.json');
    fs.writeFileSync(picksPath, JSON.stringify(picks));
    const movDir = path.join(ROOM_OUT, 'bldg');
    fs.rmSync(movDir, { recursive: true, force: true });

    const r = await cpuQueue.run(
      () => executePythonScript('populate_building.py', [
        b.ifc,
        path.join(ROOM_OUT, '_ignore.glb'),
        '--picks', picksPath,
        '--movable', movDir,
      ], { timeout: 600000 }),
      `building-populate:${b.id}`
    );
    const result = r.stdout && typeof r.stdout === 'object' ? r.stdout : null;
    if (!r.success || !result) {
      return res.status(500).json({ ok: false, error: `populate failed (exit ${r.exitCode})` });
    }
    const man = JSON.parse(fs.readFileSync(path.join(movDir, 'furniture.json'), 'utf-8'));
    const pieces = (man.pieces || []).map((p) => ({
      id: p.id, category: p.category, glb: `/out/bldg/${p.glb}`, pos: p.pos,
    }));
    res.json({
      ok: true,
      shell: '/out/bldg/shell.glb',
      pieces,
      placed: result.furniture_placed,
      rooms: result.rooms_populated,
      clashes: result.furniture_furniture_clashes,
      schedule: result.schedule || [],
    });
  } catch (err) { next(err); }
});

router.post('/building/:bid/save', async (req, res, next) => {
  try {
    const b = building(req.params.bid);
    if (!b) return res.status(404).json({ error: 'unknown building' });

    const positions = (req.body && req.body.positions) || {};
    const result = await cpuQueue.run(
      () => roomApi.call('building_save', { out_dir: ROOM_OUT, positions }, { timeout: 300000 }),
      `building-save:${b.id}`
    );
    if (result.ok === false) {
      return res.status(result.status || 500).json(result);
    }
    res.json(result);
  } catch (err) { next(err); }
});

module.exports = router;
