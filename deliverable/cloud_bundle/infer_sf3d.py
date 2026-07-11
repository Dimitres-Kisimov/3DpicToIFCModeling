"""infer_sf3d.py — batch single-image->3D with Stable Fast 3D (load ONCE, loop inputs).

LICENSE NOTE: Stability Community License — free below US$1M annual revenue.
Fine for this internal benchmark; a production adoption needs the licence check
recorded in CREDITS.md (see MODEL_SURVEY_SCS.md §8).

Runs inside the `sf3d` venv (repo Stability-AI/stable-fast-3d).

  python infer_sf3d.py manifest.json out/sf3d

Writes out/sf3d/<key>.glb per manifest item. One failure never aborts the batch.
"""
import sys, os, json, time, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

sys.path.insert(0, "/workspace/repos/stable-fast-3d")
import torch
from PIL import Image
import rembg
from sf3d.system import SF3D

device = "cuda" if torch.cuda.is_available() else "cpu"
print("[sf3d] loading stabilityai/stable-fast-3d ...", flush=True)
model = SF3D.from_pretrained("stabilityai/stable-fast-3d",
                             config_name="config.yaml", weight_name="model.safetensors")
model.to(device); model.eval()
rembg_session = rembg.new_session()
print(f"[sf3d] loaded. {len(items)} inputs.", flush=True)

for it in items:
    key = it["key"]
    out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[sf3d] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = Image.open(os.path.join(BUNDLE, it["input"])).convert("RGB")
        # sf3d expects an RGBA foreground cutout; inputs are full-frame renders
        from sf3d.utils import remove_background, resize_foreground
        img = remove_background(img, rembg_session)
        img = resize_foreground(img, 0.85)
        with torch.no_grad():
            with torch.autocast(device_type=device, dtype=torch.bfloat16) if device == "cuda" else torch.no_grad():
                mesh, _meta = model.run_image(img, bake_resolution=1024)
        mesh.export(out, include_normals=True)
        print(f"[sf3d] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[sf3d] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[sf3d] batch done.", flush=True)
