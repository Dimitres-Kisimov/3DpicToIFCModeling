"""run_cloud_benchmark.py — orchestrate the cloud 3D-gen benchmark on the pod.

Runs each model's batch inference in its OWN venv, up to --parallel at once (model-level
parallelism so a big GPU runs several at the same time), then scores everything.

  python run_cloud_benchmark.py --models triposg,trellis --parallel 2
  python run_cloud_benchmark.py --models triposg,trellis2,instantmesh,sam3d --parallel 3

Each model writes out/<model>/<key>.glb; logs to logs/<model>.log. Then score_all.py
scores out/<model>/*.glb vs the manifest ground truth and writes out/cloud_scores.csv.
"""
import os, sys, json, time, argparse, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ENVS = "/workspace/envs"

MODELS = {
    "trellis":     {"venv": "trellis",     "script": "infer_trellis.py",     "args": ["microsoft/TRELLIS-image-large"]},
    # TRELLIS.2 is a SEPARATE codebase (repo microsoft/TRELLIS.2, package trellis2,
    # o_voxel exporter) — see manuals/TRELLIS2.md; the v1 pipeline can't load it.
    "trellis2":    {"venv": "trellis2",    "script": "infer_trellis2.py",    "args": []},
    "triposg":     {"venv": "triposg",     "script": "infer_triposg.py",     "args": []},
    "instantmesh": {"venv": "instantmesh", "script": "infer_instantmesh.py", "args": []},
    "sam3d":       {"venv": "sam3d",       "script": "infer_sam3d.py",       "args": []},
    # Stability Community License: free < US$1M revenue — benchmark-only for now.
    "sf3d":        {"venv": "sf3d",        "script": "infer_sf3d.py",        "args": []},
    # Next-wave (Stage-7 licence audit 2026-07-11) — DRAFT scripts, not yet pod-proven.
    # See manuals/DIRECT3D_S2.md, STEP1X_3D.md, HI3DGEN.md, PARTCRAFTER.md.
    "direct3ds2":  {"venv": "direct3ds2",  "script": "infer_direct3ds2.py",  "args": []},
    "step1x3d":    {"venv": "step1x3d",    "script": "infer_step1x3d.py",    "args": []},
    "hi3dgen":     {"venv": "hi3dgen",     "script": "infer_hi3dgen.py",     "args": []},
    "partcrafter": {"venv": "partcrafter", "script": "infer_partcrafter.py", "args": []},
    # Census trio (docs/HF_CENSUS_2026-07.md, 2026-07-11) — DRAFT scripts, not yet pod-proven.
    # See manuals/SCENEGEN.md, CUPID.md, TOPIA_XL.md + RUNBOOK_CENSUS_TRIO.md.
    # scenegen pulls facebook/VGGT-1B (CC-BY-NC-4.0) — research benchmark ONLY, never ship.
    "scenegen":    {"venv": "scenegen",    "script": "infer_scenegen.py",    "args": []},
    "cupid":       {"venv": "cupid",       "script": "infer_cupid.py",       "args": []},
    "3dtopiaxl":   {"venv": "3dtopiaxl",   "script": "infer_3dtopiaxl.py",   "args": []},
}

ap = argparse.ArgumentParser()
ap.add_argument("--models", default="triposg,trellis")
ap.add_argument("--parallel", type=int, default=2)
ap.add_argument("--manifest", default=os.path.join(HERE, "manifest.json"))
ap.add_argument("--out", default=os.path.join(HERE, "out"))
ap.add_argument("--n", type=int, default=30000)
args = ap.parse_args()

models = [m.strip() for m in args.models.split(",") if m.strip() in MODELS]
os.makedirs(args.out, exist_ok=True)
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
n_items = len(json.load(open(args.manifest, encoding="utf-8")))
print(f"benchmark: models={models} parallel={args.parallel} items={n_items}")

def launch(m):
    spec = MODELS[m]
    outdir = os.path.join(args.out, m)
    os.makedirs(outdir, exist_ok=True)
    inner = (f'source {ENVS}/{spec["venv"]}/bin/activate && cd "{HERE}" && '
             f'python {spec["script"]} "{args.manifest}" "{outdir}" {" ".join(spec["args"])}')
    log = open(os.path.join(HERE, "logs", f"{m}.log"), "w")
    print(f"  [{time.strftime('%H:%M:%S')}] launch {m} -> logs/{m}.log")
    return subprocess.Popen(["bash", "-lc", inner], stdout=log, stderr=subprocess.STDOUT)

# run with a concurrency cap (model-level parallelism)
queue = list(models); running = {}
while queue or running:
    while queue and len(running) < args.parallel:
        m = queue.pop(0); running[m] = launch(m)
    done = [m for m, p in running.items() if p.poll() is not None]
    for m in done:
        rc = running.pop(m).returncode
        print(f"  [{time.strftime('%H:%M:%S')}] {m} finished rc={rc}")
    time.sleep(5)

print("\nall inference done -> scoring")
subprocess.run([sys.executable, os.path.join(HERE, "score_all.py"),
                args.manifest, args.out, "--n", str(args.n)], check=False)
print("\nDONE. Results: out/cloud_scores.csv + out/<model>/<key>.glb")
print("Download the whole 'out/' folder (and logs/) back to the local machine.")
