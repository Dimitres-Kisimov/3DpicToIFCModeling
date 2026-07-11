"""infer_cupid.py — batch single-image->3D with Cupid (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo README; see manuals/CUPID.md).

Licence: MIT code (cupid3d/Cupid) + MIT weights (hbb1/Cupid, TRELLIS-text-xlarge finetune)
— royalty-free, EU-safe. NAMING TRAP: code repo is github.com/cupid3d/Cupid; github.com/hbb1/Cupid
is a stale stub. Runs inside the `cupid` venv created by install_models.sh.

  python infer_cupid.py manifest.json out/cupid

Writes out/cupid/<key>.glb per manifest item (+ <key>.pose.json camera sidecar when the repo's
save_mesh emits metadata — Cupid's pose output is unique in the fleet and IFC-placement-relevant).
One failure never aborts the batch.
"""
import sys, os, json, time, glob, shutil, inspect, tempfile, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/Cupid"

# env pins BEFORE any cupid import (repo example.py pins SPCONV_ALGO itself)
os.environ.setdefault("SPCONV_ALGO", "native")    # verbatim from example.py
os.environ.setdefault("ATTN_BACKEND", "sdpa")     # flash-attn ABI gotcha #6; flip on pod if flash-attn works
sys.path.insert(0, REPO)

import torch

# --- load pipeline ONCE ------------------------------------------------------------------------
print("[cupid] loading hbb1/Cupid ...", flush=True)
from cupid.pipelines import Cupid3DPipeline
from cupid.utils import sample_utils
from cupid.utils.align_utils import save_mesh
pipe = Cupid3DPipeline.from_pretrained("hbb1/Cupid")
pipe.cuda()
SEED_KW = "seed" in inspect.signature(pipe.run).parameters   # TRELLIS heritage — unverified (manual #5)
print(f"[cupid] loaded. {len(items)} inputs. per-call seed kwarg: {SEED_KW}", flush=True)

ok = 0
for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        ok += 1
        print(f"[cupid] skip {key} (exists)", flush=True); continue
    img_path = it["input"] if os.path.isabs(it["input"]) else os.path.join(BUNDLE, it["input"])
    t0 = time.time()
    try:
        # deterministic: seed 42, same contract as every other engine in the bundle
        torch.manual_seed(42)
        image = sample_utils.load_image(img_path)          # repo's own loader (example.py verbatim)
        outputs = pipe.run(image, seed=42) if SEED_KW else pipe.run(image)
        # save_mesh writes mesh{}.glb (+ metadata.json with camera pose) into output_dir —
        # stage into a per-item temp dir, then move the first GLB to <key>.glb (manual #6).
        tmp = tempfile.mkdtemp(prefix=key + "_", dir=outdir)
        save_mesh(all_outputs=outputs, poses=outputs.pop("pose"), output_dir=tmp)
        glbs = sorted(glob.glob(os.path.join(tmp, "*.glb")))
        if not glbs:
            raise RuntimeError(f"save_mesh produced no .glb in {tmp}")
        shutil.move(glbs[0], out)
        meta = os.path.join(tmp, "metadata.json")
        if os.path.exists(meta):
            shutil.move(meta, os.path.join(outdir, key + ".pose.json"))
        shutil.rmtree(tmp, ignore_errors=True)
        ok += 1
        print(f"[cupid] OK {key} {time.time()-t0:.1f}s -> {out}", flush=True)
    except Exception as e:
        print(f"[cupid] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print(f"[cupid] batch done: {ok}/{len(items)}", flush=True)
