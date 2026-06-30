"""infer_trellis.py — batch single-image->3D with TRELLIS (load model ONCE, loop all inputs).
Runs inside the `trellis` / `trellis2` venv. Proven API from cloud/compare_4way.sh.

  python infer_trellis.py manifest.json out/trellis microsoft/TRELLIS-image-large
  python infer_trellis.py manifest.json out/trellis2 microsoft/TRELLIS.2-4B

Writes out/<model>/<key>.glb per manifest item. One failure never aborts the batch.
NOTE: TRELLIS.2-4B is assumed to share TrellisImageTo3DPipeline; if its loader differs,
the repo README for TRELLIS.2 has the right class — patch the import below.
"""
import sys, os, json, time, traceback
os.environ.setdefault("SPCONV_ALGO", "native")
os.environ.setdefault("ATTN_BACKEND", "xformers")   # flash-attn not installed; xformers backend
sys.path.insert(0, "/workspace/repos/TRELLIS")        # the `trellis` package lives in the cloned repo

manifest_path, outdir = sys.argv[1], sys.argv[2]
model_id = sys.argv[3] if len(sys.argv) > 3 else "microsoft/TRELLIS-image-large"
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

from PIL import Image
from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils

print(f"[trellis] loading {model_id} ...", flush=True)
pipe = TrellisImageTo3DPipeline.from_pretrained(model_id)
pipe.cuda()
print(f"[trellis] loaded. {len(items)} inputs.", flush=True)

for it in items:
    key = it["key"]
    out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[trellis] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = Image.open(os.path.join(BUNDLE, it["input"])).convert("RGB")
        r = pipe.run(img, seed=42)                       # deterministic seed for reproducibility
        try:
            glb = postprocessing_utils.to_glb(r["gaussian"][0], r["mesh"][0],
                                              simplify=0.95, texture_size=1024)
            glb.export(out)
        except Exception as ex:
            # mesh-only fallback — skips the diff_gaussian_rasterization texture bake.
            # Geometry is what we score (F-score) and what the grey gallery stills show.
            import trimesh
            m = r["mesh"][0]
            v = m.vertices.detach().cpu().numpy()
            f = m.faces.detach().cpu().numpy()
            trimesh.Trimesh(v, f).export(out)
            print(f"[trellis] {key}: mesh-only export (no texture: {type(ex).__name__})", flush=True)
        print(f"[trellis] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[trellis] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[trellis] batch done.", flush=True)
