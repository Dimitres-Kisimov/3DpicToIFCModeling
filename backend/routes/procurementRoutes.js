/**
 * procurementRoutes — v4: find the cheapest real, visually-similar product
 * for an AI-generated catalog item (multi-company sweep + CLIP + landed cost).
 *
 *   GET  /api/procure/targets  -> generated items that have a thumbnail (pickable)
 *   POST /api/procure          -> {item, qty?: [1,10]} -> full tiered report JSON
 *
 * The heavy work (CLIP + headless-Chrome shop sweeps) runs in
 * backend/python-scripts/procurement.py — one job at a time; results are
 * cached per (item, qty) for the session under demo/app_out/procurement/.
 */
const express = require('express');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const config = require('../config/env');
const logger = require('../middleware/logger');

const router = express.Router();
const REPO_ROOT = path.join(__dirname, '..', '..');
const ASSETS = path.join(REPO_ROOT, 'data', 'generated_assets');
const OUT_DIR = path.resolve(REPO_ROOT, config.ROOM_OUT_DIR, 'procurement');

let running = false; // CLIP + Chrome sweeps: strictly one job at a time

router.get('/procure/targets', (req, res) => {
  const items = [];
  for (const f of fs.readdirSync(ASSETS)) {
    if (f.endsWith('.thumb.png')) {
      const id = f.replace('.thumb.png', '');
      items.push({ id, thumb: `/api/generated/${f}` });
    }
  }
  res.json(items);
});

router.post('/procure', (req, res) => {
  const item = String((req.body || {}).item || '');
  if (!/^[a-z_]+-[A-Z0-9]+-\d+$/.test(item)) {
    return res.status(400).json({ ok: false, error: 'bad item id' });
  }
  const qty = (Array.isArray(req.body.qty) ? req.body.qty : [1, 10])
    .map(n => parseInt(n, 10)).filter(n => n >= 1 && n <= 500).slice(0, 3);
  if (!qty.length) qty.push(1);
  if (running) {
    return res.status(429).json({ ok: false, error: 'a procurement scan is already running — try again in a minute' });
  }
  const jsonOut = path.join(OUT_DIR, `${item}_q${qty.join('-')}.json`);
  if (fs.existsSync(jsonOut) && Date.now() - fs.statSync(jsonOut).mtimeMs < 24 * 3600e3) {
    return res.json(JSON.parse(fs.readFileSync(jsonOut, 'utf8'))); // session cache
  }
  running = true;
  const py = spawn('python', [
    path.join(REPO_ROOT, 'backend', 'python-scripts', 'procurement.py'),
    '--item', item, '--qty', ...qty.map(String), '--json', jsonOut,
  ], { cwd: REPO_ROOT });
  let err = '';
  py.stderr.on('data', d => { err += d; });
  py.on('close', (code) => {
    running = false;
    if (code === 0 && fs.existsSync(jsonOut)) {
      res.json(JSON.parse(fs.readFileSync(jsonOut, 'utf8')));
    } else {
      logger.error(`procurement failed (${code}): ${err.slice(-800)}`);
      res.status(500).json({ ok: false, error: 'procurement scan failed', detail: err.slice(-400) });
    }
  });
  req.setTimeout(15 * 60 * 1000);
});

module.exports = router;
