"""infer_trellis2.py — batch single-image->3D with TRELLIS.2-4B (load ONCE, loop inputs).

TRELLIS.2 is NOT the v1 codebase (manuals/TRELLIS2.md): separate repo
(microsoft/TRELLIS.2), package `trellis2`, O-Voxel representation, `o_voxel`
exporter. Runs inside the `trellis2` venv created by install_models.sh.

  python infer_trellis2.py manifest.json out/trellis2

Writes out/trellis2/<key>.glb per manifest item. One failure never aborts the batch.
"""
import sys, os, json, time, traceback
os.environ.setdefault("SPCONV_ALGO", "native")

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))

sys.path.insert(0, "/workspace/repos/TRELLIS2")
from PIL import Image
from trellis2.pipelines import Trellis2ImageTo3DPipeline

print("[trellis2] loading microsoft/TRELLIS.2-4B ...", flush=True)
pipe = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipe.cuda()
print(f"[trellis2] loaded. {len(items)} inputs.", flush=True)

try:
    import o_voxel
    HAVE_OVOXEL = True
except Exception:
    HAVE_OVOXEL = False
    print("[trellis2] o_voxel missing — will fall back to raw mesh export", flush=True)

for it in items:
    key = it["key"]
    out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[trellis2] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = Image.open(os.path.join(BUNDLE, it["input"])).convert("RGB")
        res = pipe.run(img, seed=42)                    # deterministic, same seed as v1 run
        mesh = res[0] if isinstance(res, (list, tuple)) else res
        exported = False
        if HAVE_OVOXEL:
            try:
                # exact args per the repo's example_image.py — adjust there if the API moved
                glb = o_voxel.postprocess.to_glb(mesh, simplify=0.95, texture_size=1024)
                glb.export(out)
                exported = True
            except Exception as oe:
                print(f"[trellis2] o_voxel export failed ({oe!r}) — raw mesh fallback", flush=True)
        if not exported:
            # mesh-only fallback (geometry is what eval_accuracy.py scores anyway)
            if hasattr(mesh, "export"):
                mesh.export(out)
            else:
                import trimesh, numpy as np
                trimesh.Trimesh(vertices=np.asarray(mesh.vertices),
                                faces=np.asarray(mesh.faces), process=True).export(out)
        print(f"[trellis2] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[trellis2] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[trellis2] batch done.", flush=True)
