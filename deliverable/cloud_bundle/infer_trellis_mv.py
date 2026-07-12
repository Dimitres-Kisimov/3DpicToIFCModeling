"""infer_trellis_mv.py — Study E: TRELLIS multi-image mode (run_multi_image).

Takes studyE_manifest.json (objects with 4 unposed views each), reconstructs
with TrellisImageTo3DPipeline.run_multi_image (stochastic mode, seed 42),
geometry-only export (Stage 8 license posture). Output out/trellis_mv/<key>.glb,
scoreable against the same GT by score_all/eval_accuracy — the direct
single-vs-multi-image comparison for the paper.

    python infer_trellis_mv.py studyE_manifest.json out/trellis_mv
"""
import sys, os, json, time, traceback
os.environ.setdefault("SPCONV_ALGO", "native")
os.environ.setdefault("ATTN_BACKEND", "sdpa")
os.environ.setdefault("SPARSE_ATTN_BACKEND", "xformers")

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

from PIL import Image
from trellis.pipelines import TrellisImageTo3DPipeline
from huggingface_hub import snapshot_download

local = snapshot_download("microsoft/TRELLIS-image-large")
pipe = TrellisImageTo3DPipeline.from_pretrained(local)
pipe.cuda()
print(f"[trellis_mv] loaded. {len(items)} objects.", flush=True)

import trimesh
ok = 0
for it in items:
    key = it["key"]
    out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        ok += 1; continue
    t0 = time.time()
    try:
        imgs = [Image.open(os.path.join(BUNDLE, v)).convert("RGB") for v in it["views"]]
        r = pipe.run_multi_image(imgs, seed=42, mode="stochastic")
        m = r["mesh"][0]
        trimesh.Trimesh(m.vertices.detach().cpu().numpy(),
                        m.faces.detach().cpu().numpy()).export(out)
        ok += 1
        print(f"[trellis_mv] OK {key} ({len(imgs)} views) {time.time()-t0:.1f}s", flush=True)
    except Exception as e:
        print(f"[trellis_mv] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print(f"[trellis_mv] batch done: {ok}/{len(items)}", flush=True)
