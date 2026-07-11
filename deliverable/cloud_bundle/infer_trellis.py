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
os.environ.setdefault("ATTN_BACKEND", "sdpa")            # dense attention (sdpa supported here)
os.environ.setdefault("SPARSE_ATTN_BACKEND", "xformers")  # sparse attention supports ONLY xformers|flash_attn
#   (v1 sparse module raises on 'sdpa'; xformers==0.0.28.post3 is the torch-2.5.1_cu121-matched wheel)

manifest_path, outdir = sys.argv[1], sys.argv[2]
model_id = sys.argv[3] if len(sys.argv) > 3 else "microsoft/TRELLIS-image-large"
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

from PIL import Image
from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils

# local snapshot load — same fix as infer_triposg (15fce17): newer hub versions
# resolve the pipeline's relative ckpt paths as repo ids ("ckpts/..." -> 404)
# unless from_pretrained gets a LOCAL directory.
from huggingface_hub import snapshot_download
print(f"[trellis] snapshot {model_id} ...", flush=True)
local = snapshot_download(model_id)
print(f"[trellis] loading {local} ...", flush=True)
pipe = TrellisImageTo3DPipeline.from_pretrained(local)
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
        glb = postprocessing_utils.to_glb(r["gaussian"][0], r["mesh"][0],
                                          simplify=0.95, texture_size=1024)
        glb.export(out)
        print(f"[trellis] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[trellis] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[trellis] batch done.", flush=True)
