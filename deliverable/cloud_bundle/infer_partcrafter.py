"""infer_partcrafter.py — batch single-image->3D with PartCrafter (load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from scripts/inference_partcrafter.py in the
repo; see manuals/PARTCRAFTER.md).

Part-level generation: one image -> PARTCRAFTER_PARTS separate part meshes (default 4), merged
into one GLB for the standard scorer; the per-part GLBs are kept alongside as <key>.parts.glb.
LICENCE NOTE: the official script masks with briaai/RMBG-1.4 (HF tag license:other — Bria
non-commercial w/o agreement). We use rembg/u2net instead, like every other engine here.
The --part_suggest Gemini path is likewise avoided (fixed num_parts, no API calls).
Licence: MIT code (c) 2025 Yuchen Lin + MIT weights (wgsxm/PartCrafter).
Runs inside the `partcrafter` venv created by install_models.sh.

  python infer_partcrafter.py manifest.json out/partcrafter
"""
import sys, os, json, time, traceback
import numpy as np

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
sys.path.insert(0, "/workspace/repos/PartCrafter")      # the `src` package lives in the cloned repo

import torch
from PIL import Image
import trimesh

NUM_PARTS = int(os.environ.get("PARTCRAFTER_PARTS", "4"))   # furniture prior: top/legs/frame/door
NUM_TOKENS = int(os.environ.get("PARTCRAFTER_TOKENS", "1024"))

# --- background removal (avoid the RMBG-1.4 licence trap — see header) ----------
try:
    from rembg import remove, new_session
    _rembg = new_session("u2net")
    def foreground(pil):
        rgba = remove(pil.convert("RGB"), session=_rembg)
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
except Exception:
    def foreground(pil):
        return pil.convert("RGB")

# --- load pipeline ONCE (local snapshot, same lesson as TripoSG) -----------------
print("[partcrafter] loading wgsxm/PartCrafter ...", flush=True)
from huggingface_hub import snapshot_download
local_dir = snapshot_download("wgsxm/PartCrafter")
from src.pipelines.pipeline_partcrafter import PartCrafterPipeline
pipe = PartCrafterPipeline.from_pretrained(local_dir).to("cuda", torch.float16)
print(f"[partcrafter] loaded from {local_dir}. {len(items)} inputs, num_parts={NUM_PARTS}.", flush=True)

for it in items:
    key = it["key"]; out = os.path.join(outdir, key + ".glb")
    if os.path.exists(out):
        print(f"[partcrafter] skip {key} (exists)", flush=True); continue
    t0 = time.time()
    try:
        img = foreground(Image.open(os.path.join(BUNDLE, it["input"])))
        with torch.no_grad():
            meshes = pipe(image=[img] * NUM_PARTS,               # image REPEATED once per part
                          attention_kwargs={"num_parts": NUM_PARTS},
                          num_tokens=NUM_TOKENS,
                          generator=torch.Generator(device=pipe.device).manual_seed(42),
                          num_inference_steps=50, guidance_scale=7.0).meshes
        parts = [m for m in meshes if m is not None and len(m.faces) > 0]
        if not parts:
            raise RuntimeError(f"all {NUM_PARTS} parts decoded to None/empty")
        if len(parts) < NUM_PARTS:
            print(f"[partcrafter] note {key}: {NUM_PARTS - len(parts)} part(s) failed to decode", flush=True)
        # merged single mesh for the scorer; part-level scene kept for the IFC decomposition track
        trimesh.util.concatenate(parts).export(out)
        try:
            trimesh.Scene(parts).export(os.path.join(outdir, key + ".parts.glb"))
        except Exception:
            pass
        print(f"[partcrafter] OK {key} {time.time()-t0:.1f}s ({len(parts)} parts) -> {out}", flush=True)
    except Exception as e:
        print(f"[partcrafter] FAIL {key}: {e!r}", flush=True)
        traceback.print_exc()
print("[partcrafter] batch done.", flush=True)
