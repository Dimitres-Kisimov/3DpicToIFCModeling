"""infer_direct3ds2.py — batch single-image->3D with Direct3D-S2 (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo README; see manuals/DIRECT3D_S2.md).

Licence: MIT code (DreamTechAI) + MIT weights (wushuang98/Direct3D-S2) — royalty-free, EU-safe.
Runs inside the `direct3ds2` venv created by install_models.sh.

  python infer_direct3ds2.py manifest.json out/direct3ds2

Writes out/direct3ds2/<key>.glb per manifest item. One failure never aborts the batch.
Resolution: 512^3 sparse SDF by default (>=10 GB VRAM); export D3S2_RES=1024 for ~24 GB.
"""
import sys, os, json, time, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
sys.path.insert(0, "/workspace/repos/Direct3D-S2")

import torch
from PIL import Image

SDF_RES = int(os.environ.get("D3S2_RES", "512"))       # 512 (>=10 GB) or 1024 (~24 GB)

# --- background removal (README examples use clean cutouts) --------------------
try:
    from rembg import remove, new_session
    _rembg = new_session("u2net")
    def foreground(pil):
        return remove(pil.convert("RGB"), session=_rembg)
except Exception:
    def foreground(pil):
        return pil.convert("RGBA")

# --- load pipeline ONCE ---------------------------------------------------------
print(f"[direct3ds2] loading wushuang98/Direct3D-S2 (subfolder direct3d-s2-v-1-1, res {SDF_RES}) ...", flush=True)
from direct3d_s2.pipeline import Direct3DS2Pipeline
pipe = Direct3DS2Pipeline.from_pretrained("wushuang98/Direct3D-S2", subfolder="direct3d-s2-v-1-1")
pipe.to("cuda:0")
print(f"[direct3ds2] loaded. {len(items)} inputs.", flush=True)

for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[direct3ds2] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        # deterministic: seed 42, same contract as every other engine in the bundle.
        # NOTE (draft): a per-call generator/seed kwarg is unverified for this pipeline —
        # the global seed is pinned instead; verify against the repo on the pod.
        torch.manual_seed(42)
        img = foreground(Image.open(os.path.join(BUNDLE, it["input"])))
        # the README example passes a file PATH — stage the cutout next to the output:
        tmp_png = os.path.join(outdir, key + ".input.png")
        img.save(tmp_png)
        mesh = pipe(tmp_png, sdf_resolution=SDF_RES, remove_interior=True, remesh=False)["mesh"]
        mesh.export(out)                                # README exports .obj; trimesh handles .glb
        os.remove(tmp_png)
        print(f"[direct3ds2] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[direct3ds2] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[direct3ds2] batch done.", flush=True)
