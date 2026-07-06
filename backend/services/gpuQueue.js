/**
 * gpuQueue — serialize GPU-heavy jobs so a small (6 GB) laptop GPU never runs two at once.
 *
 * Why: TripoSR photo→3D generation and the DETR+Depth detection pipeline each use most of the
 * 6 GB RTX 4050. Two concurrent jobs OOM and crash the box. Each job is a fresh Python subprocess
 * that fully releases VRAM on exit, so running them ONE AT A TIME is memory-safe — which is exactly
 * what lets a user add many objects iteratively without crashing.
 *
 * Concurrency = 1. Extra requests queue and run in submission order. A job that throws never breaks
 * the chain (the next job still runs). Use gpuQueue.run(fn, label) around every GPU entry point.
 */
const logger = require('../middleware/logger');

let tail = Promise.resolve();
let active = 0;
let queued = 0;
let done = 0;

function run(fn, label = 'gpu-job') {
  queued++;
  if (active + queued > 1) {
    logger.info('GPUQUEUE', `${label} waiting — GPU busy`, { active, queued });
  }
  const p = tail.then(async () => {
    queued--;
    active++;
    const t0 = Date.now();
    try {
      return await fn();
    } finally {
      active--;
      done++;
      logger.info('GPUQUEUE', `${label} finished`, { ms: Date.now() - t0, queued, done });
    }
  });
  // keep the chain alive even if this job rejects, so a failure doesn't wedge the queue
  tail = p.catch(() => {});
  return p;
}

function stats() {
  return { active, queued, done };
}

module.exports = { run, stats };
