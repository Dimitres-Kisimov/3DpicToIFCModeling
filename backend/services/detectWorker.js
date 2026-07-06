/**
 * detectWorker — Node manager for the persistent warm-model detection worker
 * (backend/python-scripts/detect_worker.py).
 *
 * Why: "Fast — from catalog" used to spend ~20 s loading DETR + Depth-Anything +
 * DINOv2 on EVERY request. The worker loads them once (SCS_WARM_MODELS=1) and
 * answers over stdin/stdout JSON lines; on CPU (CUDA hidden) so it never touches
 * the 6 GB GPU that TripoSR needs.
 *
 * Resilient by design: lazy spawn on first use, request/response correlation by
 * id with timeouts, and if the worker dies the caller falls back to the old
 * spawn-per-request path (apiRoutes catches and retries cold).
 */
const { spawn } = require('child_process');
const path = require('path');
const readline = require('readline');
const config = require('../config/env');
const logger = require('../middleware/logger');

let proc = null;
let ready = false;
let nextId = 1;
const pending = new Map();     // id -> {resolve, reject, timer}

function _cleanup(err) {
  ready = false;
  proc = null;
  for (const [, p] of pending) {
    clearTimeout(p.timer);
    p.reject(err || new Error('detect worker exited'));
  }
  pending.clear();
}

function _spawn() {
  const script = path.join(config.PYTHON_SCRIPTS_DIR, 'detect_worker.py');
  logger.info('DETECT_WORKER', 'Starting warm-model worker (CPU)');
  proc = spawn(config.PYTHON_PATH, [script], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      CUDA_VISIBLE_DEVICES: '',            // CPU only — never fight TripoSR for VRAM
      SCS_WARM_MODELS: '1',                // keep DETR/Depth/DINOv2 loaded
      SCS_TRIPOSR_SKIP_POSTPROC: '1',
      SCS_TRIPOSR_MIRROR: '0',
      SCS_RETRIEVAL_THRESHOLD: process.env.SCS_RETRIEVAL_THRESHOLD || '0',
    },
  });

  const rl = readline.createInterface({ input: proc.stdout });
  rl.on('line', (line) => {
    let msg = null;
    try { msg = JSON.parse(line.trim()); } catch (_) { return; }   // model noise — ignore
    if (msg && msg.ready) { ready = true; logger.info('DETECT_WORKER', 'Worker ready'); return; }
    const p = msg && pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    clearTimeout(p.timer);
    if (msg.error) p.reject(new Error(msg.error));
    else p.resolve(msg.result);
  });
  proc.stderr.on('data', (c) => logger.debug('DETECT_WORKER', c.toString().trim().slice(0, 300)));
  proc.on('exit', (code) => {
    logger.warn('DETECT_WORKER', `Worker exited (code ${code})`);
    _cleanup(new Error(`detect worker exited (code ${code})`));
  });
  proc.on('error', (err) => {
    logger.error('DETECT_WORKER', 'Worker spawn error', err.message);
    _cleanup(err);
  });
}

/**
 * Run detection through the warm worker. Rejects on worker failure/timeout —
 * the caller is expected to fall back to the cold spawn-per-request path.
 */
function run(imagePath, outputGlb, timeoutMs = 180000) {
  if (!proc) _spawn();
  return new Promise((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('detect worker timed out'));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    try {
      proc.stdin.write(JSON.stringify({ id, image: imagePath, out: outputGlb }) + '\n');
    } catch (e) {
      pending.delete(id);
      clearTimeout(timer);
      reject(e);
    }
  });
}

function stats() {
  return { alive: !!proc, ready, pending: pending.size };
}

module.exports = { run, stats };
