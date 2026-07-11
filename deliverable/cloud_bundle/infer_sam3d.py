"""infer_sam3d.py — batch single-image->3D with Meta SAM 3D Objects (best-effort).
Runs inside the `sam3d` venv. SAM 3D is a recent gated repo; the exact entrypoint may
differ from this guess — if so, the log lists the repo contents so it can be fixed live.
Gated weights need HUGGING_FACE_HUB_TOKEN in the environment.

  python infer_sam3d.py manifest.json out/sam3d
"""
import sys, os, json, time, glob, traceback, subprocess

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/SAM3D"

def try_api():
    """Preferred: import-based API, load model once."""
    import importlib
    for modname in ("sam_3d_objects", "sam3d_objects", "sam3d"):
        try:
            importlib.import_module(modname); return modname
        except Exception:
            continue
    return None

mod = try_api()
print(f"[sam3d] importable module: {mod}", flush=True)

ok = 0
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        ok += 1; continue
    img = os.path.join(BUNDLE, it["input"]); t0 = time.time()
    # try the documented CLI entrypoints in order; whichever produces a mesh wins
    cmds = [
        ["python", "-m", "sam_3d_objects.demo", "--image", img, "--output", out],
        ["python", "demo.py", "--image", img, "--output", out],
        ["python", "scripts/demo.py", "--input", img, "--output", out],
    ]
    produced = False
    for cmd in cmds:
        try:
            subprocess.run(cmd, cwd=REPO, check=False, timeout=600)
            if os.path.exists(out):
                produced = True; break
            # some entrypoints write to a default dir
            cand = glob.glob(os.path.join(REPO, "**", "*.glb"), recursive=True)
            if cand:
                import shutil; shutil.copy(max(cand, key=os.path.getmtime), out)
                produced = True; break
        except Exception as e:
            print(f"[sam3d] {cmd[1]} err {key}: {e!r}", flush=True)
    if produced:
        ok += 1; print(f"[sam3d] OK {key} {time.time()-t0:.1f}s", flush=True)
    else:
        print(f"[sam3d] FAIL {key} — entrypoint unknown. Repo contents:", flush=True)
        try: print("\n".join(os.listdir(REPO)), flush=True)
        except Exception: pass
print(f"[sam3d] batch done: {ok}/{len(items)}", flush=True)
