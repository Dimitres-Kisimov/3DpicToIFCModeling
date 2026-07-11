"""infer_3dtopiaxl.py — batch single-image->3D with 3DTopia-XL (PrimX; load ONCE, loop inputs).

DRAFT - not yet pod-proven (written 2026-07-11 from the repo README; see manuals/TOPIA_XL.md).

Licence: Apache-2.0 code (3DTopia/3DTopia-XL) + Apache-2.0 weights (FrozenBurning/3DTopia-XL)
— royalty-free, EU-safe. Runs inside the `3dtopiaxl` venv created by install_models.sh.

  python infer_3dtopiaxl.py manifest.json out/3dtopiaxl

Writes out/3dtopiaxl/<key>.glb per manifest item. One failure never aborts the batch.

WRAPPER PATTERN (documented deviation): 3DTopia-XL has no python API in the README — only the
config-driven `inference.py ./configs/inference_dit.yml` that walks an input_dir (doing its own
rembg cutout) and writes {output_dir}/inference_folder/{img_name}/pbr_mesh.glb per image.
Re-implementing the PrimX VAE+DiT load blind was judged higher-risk, so this driver stages the
MISSING manifest items into a temp input_dir, derives a config (absolute paths, seed 42,
export_glb True), runs the authors' inference.py ONCE (single model load, their own per-image
loop), then collects/renames each pbr_mesh.glb with per-item OK/FAIL lines. An item that the
inner loop failed simply has no pbr_mesh.glb -> logged FAIL, never a placeholder.
"""
import sys, os, json, time, glob, shutil, subprocess, traceback

manifest_path, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
items = json.load(open(manifest_path, encoding="utf-8"))
BUNDLE = os.path.dirname(os.path.abspath(manifest_path))
REPO = "/workspace/repos/3DTopia-XL"
DDIM = int(os.environ.get("TOPIA_DDIM", "25"))     # README: 25/50/100 — "Robust with more steps"

from PIL import Image

# --- stage the missing inputs into a fresh input_dir --------------------------------------------
work = os.path.join(outdir, "_topia_work")
stage = os.path.join(work, "inputs")
runout = os.path.join(work, "runout")
shutil.rmtree(work, ignore_errors=True)
os.makedirs(stage, exist_ok=True); os.makedirs(runout, exist_ok=True)

todo = []
for it in items:
    key = it["key"]
    if os.path.exists(os.path.join(outdir, key + ".glb")):
        print(f"[3dtopiaxl] skip {key} (exists)", flush=True); continue
    src = it["input"] if os.path.isabs(it["input"]) else os.path.join(BUNDLE, it["input"])
    try:
        Image.open(src).convert("RGB").save(os.path.join(stage, key + ".png"))
        todo.append(key)
    except Exception as e:
        print(f"[3dtopiaxl] FAIL {key}: staging {e!r}", flush=True)

if todo:
    # --- derive the config from the repo's own inference_dit.yml (seed 42 = its default) --------
    from omegaconf import OmegaConf
    cfg = OmegaConf.load(os.path.join(REPO, "configs/inference_dit.yml"))
    cfg.checkpoint_path = os.path.join(REPO, "pretrained/model_sview_dit_fp16.pt")
    cfg.vae_checkpoint_path = os.path.join(REPO, "pretrained/model_vae_fp16.pt")
    cfg.output_dir = runout                       # replaces ${root_data_dir}/... interpolation (manual #4)
    cfg.inference.input_dir = stage
    cfg.inference.seed = 42                       # contract seed (config default is already 42)
    cfg.inference.ddim = DDIM
    cfg.inference.export_glb = True
    derived = os.path.join(work, "inference_bench.yml")
    OmegaConf.save(cfg, derived)

    # --- one subprocess = one model load; the authors' loop handles the staged items ------------
    print(f"[3dtopiaxl] running {len(todo)} items via {REPO}/inference.py (ddim={DDIM}) ...", flush=True)
    t0 = time.time()
    rc = subprocess.run([sys.executable, "inference.py", derived], cwd=REPO).returncode
    print(f"[3dtopiaxl] inference.py rc={rc} ({time.time()-t0:.0f}s) — collecting outputs", flush=True)

    # --- collect: {output_dir}/**/pbr_mesh.glb, parent dir named after the staged file (manual #5)
    produced = {}
    for p in glob.glob(os.path.join(runout, "**", "pbr_mesh.glb"), recursive=True):
        produced[os.path.basename(os.path.dirname(p))] = p
    for key in todo:
        out = os.path.join(outdir, key + ".glb")
        hit = produced.get(key) or produced.get(key + ".png")
        if hit is None:                            # tolerate other img_name derivations
            cands = [p for d, p in produced.items() if d.startswith(key)]
            hit = cands[0] if cands else None
        try:
            if hit is None or os.path.getsize(hit) == 0:
                raise RuntimeError("no pbr_mesh.glb produced (see inference.py output above)")
            shutil.copyfile(hit, out)
            print(f"[3dtopiaxl] OK {key} -> {out}", flush=True)
        except Exception as e:
            print(f"[3dtopiaxl] FAIL {key}: {e!r}", flush=True)
            traceback.print_exc()

shutil.rmtree(work, ignore_errors=True)
n_ok = len(glob.glob(os.path.join(outdir, "*.glb")))
print(f"[3dtopiaxl] batch done: {n_ok}/{len(items)}", flush=True)
