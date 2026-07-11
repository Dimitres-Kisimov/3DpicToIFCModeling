"""infer_triposg.py — batch single-image->3D with VAST-AI/TripoSG (load ONCE, loop).
Runs inside the `triposg` venv.

  python infer_triposg.py manifest.json out/triposg

Best-effort from the TripoSG repo (VAST-AI-Research/TripoSG, scripts/inference_triposg.py).
If the pipeline import path differs in the installed version, patch the import block — the
repo README shows the exact loader. One failure never aborts the batch.
"""
import sys, os, json, time, traceback
import numpy as np

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
sys.path.insert(0, "/workspace/repos/TripoSG")   # the `triposg` package lives in the cloned repo

import torch
from PIL import Image
import trimesh

# --- background removal (TripoSG expects a clean foreground) ------------------
try:
    from rembg import remove, new_session
    _rembg = new_session("u2net")
    def foreground(pil):
        return remove(pil, session=_rembg).convert("RGB")
except Exception:
    def foreground(pil):
        return pil.convert("RGB")

# --- load pipeline ONCE -------------------------------------------------------
# TripoSG's custom pipeline must load from a LOCAL snapshot (it needs the repo
# structure on disk + the `triposg` package on sys.path for its custom scheduler).
print("[triposg] loading VAST-AI/TripoSG ...", flush=True)
from huggingface_hub import snapshot_download
local_dir = snapshot_download("VAST-AI/TripoSG")
from triposg.pipelines.pipeline_triposg import TripoSGPipeline
pipe = TripoSGPipeline.from_pretrained(local_dir).to("cuda", torch.float16)
print(f"[triposg] loaded from {local_dir}. {len(items)} inputs.", flush=True)

def to_mesh(out):
    """Normalize TripoSG output (verts,faces tuple OR object with .vertices/.faces) to a Trimesh."""
    if isinstance(out, trimesh.Trimesh):
        return out
    if hasattr(out, "vertices") and hasattr(out, "faces"):
        return trimesh.Trimesh(np.asarray(out.vertices, np.float32), np.asarray(out.faces))
    v, f = out[0], out[1]
    return trimesh.Trimesh(np.asarray(v, np.float32), np.ascontiguousarray(f))

for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[triposg] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = foreground(Image.open(os.path.join(BUNDLE, it["input"])))
        gen = torch.Generator(device="cuda").manual_seed(42)
        res = pipe(image=img, generator=gen, num_inference_steps=50, guidance_scale=7.0)
        samples = getattr(res, "samples", res)
        mesh = to_mesh(samples[0] if isinstance(samples, (list, tuple)) else samples)
        mesh.export(out)
        print(f"[triposg] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[triposg] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[triposg] batch done.", flush=True)
