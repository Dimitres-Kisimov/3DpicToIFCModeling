"""install_engine.py — install a 3D engine LOCALLY through the app, from the
registry recipe (backend/config/engines.json), which mirrors the battle-tested
manual in deliverable/manuals/. Called by POST /api/engines/:id/install after
the server has verified this machine meets the baseline (VRAM, OS, disk).

    python install_engine.py <engine_id> [--dry-run] [--engines-dir DIR]

Layout produced under the engines dir:
    envs/<id>/            the engine's own virtualenv
    repos/<...>           cloned sources
    weights/<repo>        HuggingFace snapshots
    bundle/               the infer scripts (copied once from deliverable/cloud_bundle)
    <id>.install.log      full transcript
    envs/<id>/.ready      marker consumed by bigEngine.listEngines()
Exit 0 = installed + smoke test passed. Idempotent: a .ready venv is left alone.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = json.loads((REPO / "backend" / "config" / "engines.json").read_text(encoding="utf-8"))

eid = sys.argv[1] if len(sys.argv) > 1 else ""
DRY = "--dry-run" in sys.argv
ENG_DIR = Path(sys.argv[sys.argv.index("--engines-dir") + 1]) if "--engines-dir" in sys.argv \
    else Path(os.environ.get("SCS_ENGINES_DIR") or (REPO / "engines"))

eng = next((e for e in REGISTRY["engines"] if e["id"] == eid), None)
if not eng or eng.get("builtin") or "install" not in eng:
    print(f"ERROR: '{eid}' is not an installable engine", file=sys.stderr)
    sys.exit(2)
rec = eng["install"]

LOG = ENG_DIR / f"{eid}.install.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if not DRY:
        ENG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def run(cmd, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    if DRY:
        return
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace", **kw)
    if not DRY:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(r.stdout[-8000:] + "\n")
    if r.returncode != 0:
        log(f"FAILED (exit {r.returncode}) — last output:\n{r.stdout[-1500:]}")
        sys.exit(1)


venv = ENG_DIR / eng["venv"]
ready = venv / ".ready"
if ready.exists() and not DRY:
    log("already installed (.ready present) — nothing to do")
    sys.exit(0)

log(f"=== installing {eng['label']} ===")
log(f"engines dir: {ENG_DIR} | recipe python {rec.get('python')} | ~{rec.get('disk_gb')} GB disk")

# 1) venv
py = sys.executable
vpy = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not vpy.exists():
    run([py, "-m", "venv", str(venv)])
log(f"venv: {venv}")

# 2) recipe steps
dest_root = None
for step in rec.get("steps", []):
    t = step["type"]
    if t == "clone":
        dest = ENG_DIR / step["dest"]
        dest_root = dest
        if dest.exists():
            log(f"clone exists: {dest}")
        else:
            run(["git", "clone", "--depth", "1", step["repo"], str(dest)])
    elif t == "pip":
        args = [a.replace("{dest}", str(dest_root or "")) for a in step["args"]]
        run([str(vpy), "-m", "pip", "install", "-q"] + args)
    elif t == "kaolin_stub":
        # TRELLIS uses only kaolin.utils.testing.check_tensor — stub it
        # (manual issue #5: full kaolin needs matched wheels we don't want)
        log("writing kaolin stub (check_tensor only)")
        if not DRY:
            import sysconfig
            r = subprocess.run([str(vpy), "-c",
                                "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                               capture_output=True, text=True)
            site = Path(r.stdout.strip())
            (site / "kaolin" / "utils").mkdir(parents=True, exist_ok=True)
            (site / "kaolin" / "__init__.py").write_text("")
            (site / "kaolin" / "utils" / "__init__.py").write_text("")
            (site / "kaolin" / "utils" / "testing.py").write_text(
                "def check_tensor(*a, **k):\n    return True\n")
    else:
        log(f"unknown step type: {t}")
        sys.exit(2)

# 3) weights
for repo in rec.get("weights", []):
    tgt = ENG_DIR / "weights" / repo.replace("/", "__")
    log(f"weights: {repo} -> {tgt}")
    if not DRY:
        run([str(vpy), "-c",
             "from huggingface_hub import snapshot_download;"
             f"snapshot_download('{repo}', local_dir=r'{tgt}')"])

# 4) infer scripts bundle (once)
bundle = ENG_DIR / "bundle"
if not DRY:
    bundle.mkdir(parents=True, exist_ok=True)
    for f in (REPO / "deliverable" / "cloud_bundle").glob("infer_*.py"):
        shutil.copy(f, bundle / f.name)
log(f"bundle: {bundle}")

# 5) smoke test, then the ready marker
if rec.get("smoke"):
    run([str(vpy), "-c", rec["smoke"]])
if not DRY:
    ready.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
log("=== INSTALL COMPLETE — engine is now selectable in the app ===")
