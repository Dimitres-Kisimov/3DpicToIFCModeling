/**
 * roomApi — Node bridge to backend/python-scripts/room_api.py, the single Python
 * dispatcher that carries every room / building / catalog operation (the engine
 * the retired Flask app used in-process).
 *
 * Contract: `python room_api.py <command> @<args.json>` prints a JSON result as
 * the LAST stdout line (parsed by pythonBridge). Args always travel via a temp
 * file — inline JSON on a Windows command line is a quoting minefield.
 *
 * Caching: `catalog` and `items` results are cached in-memory here (the data only
 * changes when an upload registers a new asset), so browsing the catalog costs
 * zero Python spawns after first load. invalidateCatalog() is called on upload —
 * and by the generator flow when it auto-registers a new mesh (B3).
 *
 * When the warm-model worker lands (Workstream D), only this file changes:
 * call() switches from spawn-per-request to writing a command line to the
 * persistent worker's stdin. Every route keeps the same request/response shape.
 */
const fs = require('fs');
const path = require('path');
const { executePythonScript } = require('./pythonBridge');
const config = require('../config/env');
const logger = require('../middleware/logger');

let _seq = 0;

async function call(command, args = {}, opts = {}) {
  fs.mkdirSync(config.TEMP_DIR, { recursive: true });
  const tmp = path.join(config.TEMP_DIR, `roomapi_${command}_${Date.now()}_${_seq++}.json`);
  fs.writeFileSync(tmp, JSON.stringify(args));
  try {
    const r = await executePythonScript('room_api.py', [command, '@' + tmp], {
      timeout: opts.timeout || 300000,
    });
    const out = r.stdout && typeof r.stdout === 'object' ? r.stdout : null;
    if (!r.success || !out) {
      const err = new Error(`room_api ${command} failed (exit ${r.exitCode})`);
      err.statusCode = 500;
      err.details = { stderr: String(r.stderr || '').slice(-2000) };
      throw err;
    }
    if (out.ok === false) {
      logger.warn('ROOM_API', `${command} returned error`, { error: out.error });
    }
    return out;
  } finally {
    try { fs.unlinkSync(tmp); } catch (_) { /* temp cleanup is best-effort */ }
  }
}

// ---------------------------------------------------------------------------
// catalog caching — zero repeated Python spawns for browsing
// ---------------------------------------------------------------------------
let _catalogCache = null;               // categories array
const _itemsCache = new Map();          // category -> items array

async function getCatalog() {
  if (_catalogCache) return _catalogCache;
  const res = await call('catalog', {}, { timeout: 60000 });
  if (res.ok === false) throw Object.assign(new Error(res.error), { statusCode: 500 });
  _catalogCache = res.categories;
  return _catalogCache;
}

async function getItems(category) {
  if (_itemsCache.has(category)) return _itemsCache.get(category);
  const res = await call('items', { category }, { timeout: 60000 });
  if (res.ok === false) throw Object.assign(new Error(res.error), { statusCode: 500 });
  _itemsCache.set(category, res.items);
  return res.items;
}

function invalidateCatalog(category) {
  _catalogCache = null;
  if (category) _itemsCache.delete(category);
  else _itemsCache.clear();
}

module.exports = { call, getCatalog, getItems, invalidateCatalog };
