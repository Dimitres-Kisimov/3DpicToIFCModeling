/**
 * bigEngine.js — generic adapter for the external "big" engines
 * (TripoSG / TRELLIS.2 / SAM 3D) defined in backend/config/engines.json.
 *
 * These never run on an under-spec machine: /api/engines gates them by VRAM
 * and by whether SCS_ENGINES_DIR holds their venv (the restored pod archive).
 * Each generation is one subprocess in the engine's own venv — same
 * load-run-exit pattern as the TripoSR path, so idle VRAM stays at zero and
 * the gpuQueue guarantees only one GPU job at a time.
 *
 * Flow per request: write a one-item manifest -> run the engine's infer
 * script (the exact script the cloud benchmark used) -> repair packs in the
 * app's pinned Python (repair_glb.py) -> outputs/.
 */

const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');
const config = require('../config/env');
const logger = require('../middleware/logger');

const REGISTRY = require('../config/engines.json');

function enginesDir() {
  // default to <repo>/engines — the in-app installer manages this directory;
  // SCS_ENGINES_DIR still overrides (e.g. a restored pod archive elsewhere)
  return process.env.SCS_ENGINES_DIR || path.join(__dirname, '..', '..', 'engines');
}

function getEngine(id) {
  return (REGISTRY.engines || []).find((e) => e.id === id) || null;
}

/** Detected total VRAM in GB (0 when nvidia-smi is unavailable). Cached. */
let _vramGb = null;
function detectVramGb() {
  if (_vramGb !== null) return Promise.resolve(_vramGb);
  return new Promise((resolve) => {
    const p = spawn('nvidia-smi', ['--query-gpu=memory.total', '--format=csv,noheader,nounits']);
    let out = '';
    p.stdout.on('data', (c) => { out += c; });
    p.on('error', () => { _vramGb = 0; resolve(0); });
    p.on('close', () => {
      const mb = parseInt(out.trim().split('\n')[0], 10);
      _vramGb = Number.isFinite(mb) ? Math.round(mb / 1024) : 0;
      resolve(_vramGb);
    });
  });
}

/** Availability + human reason + INSTALLABILITY for every engine on THIS machine.
 *  An engine is installable in-app when: it has a recipe, the OS is supported
 *  (recipes are Linux/WSL-proven — see the manuals), and VRAM meets the baseline.
 */
async function listEngines() {
  const vram = await detectVramGb();
  const dir = enginesDir();
  const osName = process.platform === 'win32' ? 'windows'
    : process.platform === 'darwin' ? 'mac' : 'linux';
  return (REGISTRY.engines || []).map((e) => {
    let available = true;
    let reason = '';
    let installed = true;
    let installable = false;
    let installState = 'n/a';
    if (!e.builtin) {
      installed = !!(dir && fs.existsSync(path.join(dir, e.venv || '', '.ready')));
      const rec = e.install || null;
      const osOk = rec && (rec.os || []).includes(osName);
      const vramOk = vram >= e.min_vram_gb;
      installable = !!(rec && osOk && vramOk && !installed);
      const logP = path.join(dir, `${e.id}.install.log`);
      installState = installed ? 'ready'
        : fs.existsSync(path.join(dir, `${e.id}.installing`)) ? 'installing'
        : fs.existsSync(logP) ? 'failed' : 'none';
      if (!vramOk) {
        available = false;
        reason = `Needs a ${e.min_vram_gb} GB graphics card — this machine has ${vram || 'no NVIDIA'} GB`;
      } else if (!installed) {
        available = false;
        reason = rec && !osOk
          ? `Install needs Linux/WSL (compiled CUDA extensions) — see ${e.manual}`
          : `Not installed yet — one-click install available (~${(rec && rec.disk_gb) || '?'} GB)`;
      }
    }
    return {
      id: e.id, abbr: e.abbr, label: e.label, builtin: !!e.builtin,
      min_vram_gb: e.min_vram_gb, license: e.license, manual: e.manual,
      notes: e.notes, available, reason,
      installed, installable, install_state: installState,
      disk_gb: (e.install && e.install.disk_gb) || null,
    };
  });
}

function runProc(cmd, args, opts, logTag) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, opts);
    let stdout = '', stderr = '';
    child.stdout.on('data', (c) => { stdout += c.toString(); });
    child.stderr.on('data', (c) => { stderr += c.toString(); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        logger.error('BIGENGINE', `${logTag} exited ${code}`, { stderr: stderr.slice(-600) });
        return reject(new Error(`${logTag} failed: ${stderr.slice(-300) || stdout.slice(-300)}`));
      }
      resolve({ stdout, stderr });
    });
  });
}

/**
 * Generate with a big engine. Returns { glbPath, glbUrl, engine, faces }.
 * Call through gpuQueue — this does NOT queue itself.
 */
async function runBigEngine(engineId, imagePath, outputDir) {
  const eng = getEngine(engineId);
  if (!eng || eng.builtin) throw new Error(`not a big engine: ${engineId}`);
  const dir = enginesDir();
  const venvPy = path.join(dir, eng.venv, 'bin', 'python');
  const venvPyWin = path.join(dir, eng.venv, 'Scripts', 'python.exe');
  const python = fs.existsSync(venvPyWin) ? venvPyWin : venvPy;
  if (!fs.existsSync(python)) throw new Error(`engine venv missing: ${eng.venv}`);
  const script = path.join(dir, 'bundle', eng.script);
  if (!fs.existsSync(script)) throw new Error(`engine script missing: ${eng.script}`);

  // one-item manifest, same shape the cloud benchmark scripts consume
  const key = `gen_${Date.now()}`;
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'scs-bigengine-'));
  const manifest = path.join(work, 'manifest.json');
  fs.writeFileSync(manifest, JSON.stringify([{ key, type: 'object', input: imagePath }]));

  logger.info('BIGENGINE', `generation start`, { engine: engineId, key });
  await runProc(python, [script, manifest, work], { cwd: work }, `${engineId} infer`);
  const rawGlb = path.join(work, `${key}.glb`);
  if (!fs.existsSync(rawGlb)) throw new Error(`${engineId} produced no mesh`);

  // repair packs in the app's pinned Python, then land in outputs/
  const outName = `mesh_${Date.now()}_${eng.abbr.toLowerCase()}.glb`;
  const outGlb = path.join(outputDir, outName);
  const repairScript = path.join(__dirname, '..', 'python-scripts', 'repair_glb.py');
  const appPy = config.PYTHON_PATH || 'python';
  const rep = await runProc(appPy, [repairScript, rawGlb, outGlb, 'object'],
    { cwd: path.join(__dirname, '..', '..') }, 'repair_glb');
  let faces = null;
  try { faces = JSON.parse(rep.stdout.trim().split('\n').pop()).faces; } catch (_) { /* stats only */ }

  try { fs.rmSync(work, { recursive: true, force: true }); } catch (_) { /* temp */ }
  return { glbPath: outGlb, glbUrl: `/outputs/${outName}`, engine: eng.abbr, faces };
}

module.exports = { listEngines, getEngine, runBigEngine, detectVramGb };
