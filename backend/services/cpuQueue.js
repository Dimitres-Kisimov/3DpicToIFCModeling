/**
 * cpuQueue — bound heavy CPU jobs (layout solver, building populate, GLB merges)
 * so a burst of requests can't pile up Python processes and starve the box.
 *
 * Why: each of these jobs spawns a Python subprocess that can hold hundreds of MB
 * (trimesh scenes, ifcopenshell models, CP-SAT search). Two at a time is fine on the
 * dev laptop and the GEX44; an unbounded pile-up is what actually "tampers with
 * performance". GPU work has its own stricter queue (gpuQueue, concurrency 1).
 *
 * Concurrency = CPU_JOB_CONCURRENCY (default 2). Extra requests wait in FIFO order.
 * A job that throws never wedges the queue. Use cpuQueue.run(fn, label).
 */
const logger = require('../middleware/logger');

const LIMIT = parseInt(process.env.CPU_JOB_CONCURRENCY, 10) || 2;

let active = 0;
let done = 0;
const waiting = [];

function _next() {
  while (active < LIMIT && waiting.length > 0) {
    const { fn, label, resolve, reject } = waiting.shift();
    active++;
    const t0 = Date.now();
    Promise.resolve()
      .then(fn)
      .then(resolve, reject)
      .finally(() => {
        active--;
        done++;
        logger.info('CPUQUEUE', `${label} finished`, { ms: Date.now() - t0, waiting: waiting.length, done });
        _next();
      });
  }
}

function run(fn, label = 'cpu-job') {
  return new Promise((resolve, reject) => {
    if (active >= LIMIT) {
      logger.info('CPUQUEUE', `${label} waiting — ${active} job(s) running`, { waiting: waiting.length + 1 });
    }
    waiting.push({ fn, label, resolve, reject });
    _next();
  });
}

function stats() {
  return { active, waiting: waiting.length, done, limit: LIMIT };
}

module.exports = { run, stats };
