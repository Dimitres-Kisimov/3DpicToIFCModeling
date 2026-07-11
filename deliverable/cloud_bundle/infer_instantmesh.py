"""infer_instantmesh.py — batch single-image->3D with TencentARC/InstantMesh.
Runs inside the `instantmesh` venv. On 80GB the 8GB 'collapsed-cube' hack is NOT needed —
runs native at full res. InstantMesh's run.py loads the model once and accepts a directory
of images, so we stage all inputs into one dir, run once, then collect + convert .obj->.glb.

  python infer_instantmesh.py manifest.json out/instantmesh
"""
import sys, os, json, time, shutil, subprocess, glob, traceback

# outdir MUST be absolute: run.py executes with cwd=REPO, so a relative staging
# path resolves against the repo, not the bundle (caused the 0/170 MISSING-obj run)
manifest_path, outdir = sys.argv[1], os.path.abspath(sys.argv[2])
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/InstantMesh"

# stage inputs into one dir, named by key so outputs are identifiable
stage = os.path.join(outdir, "_inputs")
os.makedirs(stage, exist_ok=True)
for it in items:
    shutil.copy(os.path.join(BUNDLE, it["input"]), os.path.join(stage, it["key"] + ".png"))

run_out = os.path.join(outdir, "_run")
print(f"[instantmesh] running run.py on {len(items)} inputs (loads model once) ...", flush=True)
t0 = time.time()
try:
    subprocess.run(
        ["python", "run.py", "configs/instant-mesh-base.yaml", stage,
         "--output_path", run_out, "--no_rembg"],
        cwd=REPO, check=False)
except Exception as e:
    print(f"[instantmesh] run.py error: {e!r}", flush=True); traceback.print_exc()

# collect .obj (InstantMesh writes meshes/<name>.obj) and convert to glb
import trimesh
found = 0
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    cand = (glob.glob(os.path.join(run_out, "**", "meshes", key + ".obj"), recursive=True)
            or glob.glob(os.path.join(REPO, "outputs", "**", "meshes", key + ".obj"), recursive=True))
    if cand:
        try:
            trimesh.load(cand[0], force="mesh").export(out)
            found += 1
            print(f"[instantmesh] OK {key} -> {out}", flush=True)
        except Exception as e:
            print(f"[instantmesh] convert FAIL {key}: {e!r}", flush=True)
    else:
        print(f"[instantmesh] MISSING obj for {key}", flush=True)
print(f"[instantmesh] batch done: {found}/{len(items)} in {time.time()-t0:.1f}s", flush=True)
