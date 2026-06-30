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
# Our inputs are rendered on a WHITE background, so threshold it directly — avoids a
# rembg/onnxruntime dependency conflict with SAM 3D's pinned (numpy 1.26.4) environment.
def rgba_and_mask(path):
    img = Image.open(path).convert("RGB")
    arr = np.array(img)
    fg = (np.abs(arr.astype(int) - 255).sum(2) > 30).astype(np.uint8)
    return arr, fg  # Meta merge_mask_to_rgba expects numpy RGB image + numpy 0/1 mask

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
# --- utils3d viz-function shims (SceneVisualizer/image_mesh import these at module load;
# they live in the pointmap-visualization path, NOT the mesh-decoder inference we call) -----
import numpy as _np_shim
def _nrm_edge(normals, *a, **k):
    n = _np_shim.asarray(normals); return _np_shim.zeros(n.shape[:2], dtype=bool)
def _pts2nrm(points, *a, **k):
    p = _np_shim.asarray(points, dtype=_np_shim.float32); o = _np_shim.zeros_like(p); o[..., 2] = 1.0; return o
def _img_uv(height, width, *a, **k):
    u = (_np_shim.arange(width) + 0.5) / width; v = (_np_shim.arange(height) + 0.5) / height
    uu, vv = _np_shim.meshgrid(u, v); return _np_shim.stack([uu, vv], -1).astype(_np_shim.float32)
def _img_mesh(*a, **k):
    raise NotImplementedError("image_mesh shim (viz-only, not used in mesh-decoder inference)")
for _n, _fn in [("normals_edge", _nrm_edge), ("points_to_normals", _pts2nrm),
                ("image_uv", _img_uv), ("image_mesh", _img_mesh)]:
    if not hasattr(_u3n, _n):
        setattr(_u3n, _n, _fn)
print("[sam3d] importing Meta Inference ...", flush=True)
from inference import Inference  # type: ignore

pipe_yaml = find_pipeline_yaml()
print(f"[sam3d] loading pipeline {pipe_yaml} (60-120s) ...", flush=True)
inference = Inference(pipe_yaml, compile=False)
print(f"[sam3d] loaded. {len(items)} inputs.", flush=True)

import trimesh

def _to_trimesh(m):
    """Coerce a SAM3D mesh-ish object (possibly a batch list) into trimesh.Trimesh."""
    if isinstance(m, (list, tuple)):
        m = m[0] if len(m) else None
    if m is None:
        return None
    if isinstance(m, trimesh.Trimesh):
        return m
    if hasattr(m, "vertices") and hasattr(m, "faces"):
        v, fc = m.vertices, m.faces
        v = v.detach().cpu().numpy() if hasattr(v, "detach") else np.asarray(v)
        fc = fc.detach().cpu().numpy() if hasattr(fc, "detach") else np.asarray(fc)
        col = None
        for attr in ("vertex_colors", "visual", "vertex_attrs"):
            cc = getattr(m, attr, None)
            if cc is not None and hasattr(cc, "__len__") and len(cc) == len(v):
                col = cc.detach().cpu().numpy() if hasattr(cc, "detach") else np.asarray(cc)
                break
        return trimesh.Trimesh(vertices=v, faces=fc, vertex_colors=col, process=False)
    if hasattr(m, "export"):
        return m
    return None

_dumped = False
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[sam3d] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        arr, fg = rgba_and_mask(os.path.join(BUNDLE, it["input"]))
        output = inference(arr, fg, seed=42)
        if not _dumped:
            if isinstance(output, dict):
                print("[sam3d] OUTPUT KEYS:", list(output.keys()), flush=True)
                for k, vv in output.items():
                    info = f"  [{k}] {type(vv).__name__}"
                    if isinstance(vv, (list, tuple)):
                        info += f" len={len(vv)} elem0={type(vv[0]).__name__ if vv else None}"
                        if vv and hasattr(vv[0], "vertices"):
                            try: info += f" v={len(vv[0].vertices)} f={len(vv[0].faces)}"
                            except Exception: pass
                    if hasattr(vv, "shape"):
                        info += f" shape={tuple(vv.shape)}"
                    print(info, flush=True)
            else:
                print("[sam3d] OUTPUT TYPE:", type(output).__name__, flush=True)
            _dumped = True
        mesh = None
        if isinstance(output, dict):
            for k in ("mesh", "meshes", "trimesh", "glb", "geometry", "gaussian"):
                if k in output and output[k] is not None:
                    mesh = _to_trimesh(output[k])
                    if mesh is not None:
                        break
        else:
            mesh = _to_trimesh(output)
        if mesh is None:
            ks = list(output.keys()) if isinstance(output, dict) else type(output).__name__
            print(f"[sam3d] FAIL {key}: could not coerce mesh; out={ks}", flush=True); continue
        mesh.export(out)
        print(f"[sam3d] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[sam3d] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[sam3d] batch done.", flush=True)
