"""infer_sam3d.py — batch SAM 3D Objects using Meta's REAL inference entrypoint.
Recipe recovered from the project's `sam3d-integration-wip` branch (run_sam3d.py).
On the Linux pod pytorch3d/kaolin install directly, so no Windows stubs are needed.
Loads the pipeline ONCE, loops all inputs. Needs gated weights (HF token at install).

  python infer_sam3d.py manifest.json out/sam3d
"""
import sys, os, json, time, traceback
from pathlib import Path
import numpy as np
from PIL import Image

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
CLONE = "/workspace/repos/SAM3D"

# --- foreground mask (SAM 3D takes image + mask) ------------------------------
from rembg import remove, new_session
_sess = new_session("u2net")
def rgba_and_mask(path):
    img = Image.open(path)
    rgba = img if img.mode == "RGBA" else remove(img, session=_sess).convert("RGBA")
    arr = np.array(rgba)
    mask = Image.fromarray((arr[:, :, 3] > 128).astype(np.uint8) * 255, mode="L")
    return rgba, mask

# --- locate the downloaded checkpoint config ----------------------------------
def find_pipeline_yaml():
    base = (Path.home() / ".cache" / "huggingface" / "hub" /
            "models--facebook--sam-3d-objects" / "snapshots")
    snap = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime)[-1]
    return str(snap / "checkpoints" / "pipeline.yaml")

# --- Meta's Inference class (notebook/inference.py) ---------------------------
sys.path.insert(0, CLONE)
sys.path.insert(0, os.path.join(CLONE, "notebook"))
# Meta's notebook/inference.py does `CUDA_HOME = os.environ["CONDA_PREFIX"]` which
# KeyErrors under a venv (no conda). Provide a sane default (the branch's adapter fix).
os.environ.setdefault("CONDA_PREFIX", "/usr/local/cuda")
os.environ.setdefault("LIDRA_SKIP_INIT", "true")
# utils3d 1.7 dropped depth_edge (SAM3D uses it only in a VISUALIZATION util, not the forward path) —
# inject a compatible implementation so the import chain resolves.
import utils3d.numpy as _u3n
if not hasattr(_u3n, "depth_edge"):
    from scipy.ndimage import maximum_filter as _maxf, minimum_filter as _minf
    def _depth_edge(depth, atol=None, rtol=0.05, kernel_size=3, mask=None):
        d = np.asarray(depth, dtype=np.float32)
        edge = (_maxf(d, size=kernel_size) - _minf(d, size=kernel_size)) > (rtol * np.abs(d) + (atol or 0.0))
        return (edge & np.asarray(mask, bool)) if mask is not None else edge
    _u3n.depth_edge = _depth_edge
print("[sam3d] importing Meta Inference ...", flush=True)
from inference import Inference  # type: ignore

pipe_yaml = find_pipeline_yaml()
print(f"[sam3d] loading pipeline {pipe_yaml} (60-120s) ...", flush=True)
inference = Inference(pipe_yaml, compile=False)
print(f"[sam3d] loaded. {len(items)} inputs.", flush=True)

import trimesh
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[sam3d] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        rgba, mask = rgba_and_mask(os.path.join(BUNDLE, it["input"]))
        output = inference(rgba, mask, seed=42)         # mesh-decoder path
        mesh = output.get("mesh") or output.get("trimesh")
        if mesh is None:
            print(f"[sam3d] FAIL {key}: no mesh; keys={list(output.keys())}", flush=True); continue
        if hasattr(mesh, "export"):
            mesh.export(out)
        else:
            trimesh.Trimesh(np.asarray(mesh.vertices), np.asarray(mesh.faces)).export(out)
        print(f"[sam3d] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[sam3d] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[sam3d] batch done.", flush=True)
