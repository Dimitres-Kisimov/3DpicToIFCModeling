"""precompute_masks.py — rembg foreground masks for every manifest input.

SAM 3D needs an explicit mask; internet photos (the 170/187 sweep) have arbitrary
backgrounds, so the white-bg heuristic fails there. rembg conflicts with SAM 3D's
numpy==1.26.4 pin (manual fix #8), so masks are precomputed HERE in a different
env (any env with rembg, e.g. triposg's) and read by infer_sam3d.py.

  python precompute_masks.py manifest.json masks/
"""
import sys, os, json

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

from PIL import Image
from rembg import remove, new_session

session = new_session("u2net")
done = 0
for it in items:
    key = it["key"]
    dst = os.path.join(outdir, key + ".png")
    if os.path.exists(dst):
        done += 1
        continue
    src = it["input"] if os.path.isabs(it["input"]) else os.path.join(BUNDLE, it["input"])
    try:
        img = Image.open(src).convert("RGB")
        cut = remove(img, session=session)            # RGBA
        cut.split()[-1].point(lambda a: 255 if a > 40 else 0).save(dst)  # alpha -> binary mask
        done += 1
        print(f"[masks] {key}", flush=True)
    except Exception as e:
        print(f"[masks] FAIL {key}: {e!r}", flush=True)
print(f"[masks] done: {done}/{len(items)}", flush=True)
