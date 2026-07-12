# Manual: 3DTopia-XL (NTU) — 🟡 DRAFT — census-trio candidate, not yet pod-proven (2026-07-11)

> **DRAFT.** Written from the repo README + LICENSE + HF API (all fetched 2026-07-11),
> **not** from a completed pod run. Install steps, entry point and the issues table are *anticipated*;
> fill in the real fix chain after the first run, like the proven manuals (TripoSG.md, SAM3D.md).

> **Campaign note — gate failed (2026-07-12, A100):** 3DTopia-XL got two slots. Its `newwave.sh`
> preflight gate **failed on the draft recipe** (slot skipped by policy — no GPU debugging loops), and
> the `endgame.sh` retry (install already paid for) **did not land a verified >50 KB mesh before the pod
> hit zero balance** — no 3DTopia-XL item reached the catalog. The `EG_TOPIA_GATE_*` log lines and any
> late meshes are recoverable from the stopped pod's volume via a top-up. **The DRAFT banner stands.**

**Why we test it:** #3 of the three challengers from the full HuggingFace tag census
([HF_CENSUS_2026-07.md](../../docs/HF_CENSUS_2026-07.md)) — the only **permissive PBR-native**
mesh generator in the whole tag (PrimX primitive diffusion → mesh with albedo/roughness/metallic),
~5 s claimed inference. Census expectation: *"probably loses to TripoSG on F-score but closes the
census"* — running it buys the negative result that makes the census exhaustive.

## Licence (verbatim)

Code `LICENSE.txt` (github.com/3DTopia/3DTopia-XL — via the GitHub licence API, fetched 2026-07-11;
note the file is `LICENSE.txt`, raw `LICENSE` 404s):

> Apache License
> Version 2.0, January 2004
> http://www.apache.org/licenses/

SPDX id reported by GitHub: **Apache-2.0**. Weights `FrozenBurning/3DTopia-XL` — HF API tag
**`license:apache-2.0`**, `gated: False` (verified 2026-07-11).
Code Apache-2.0 + weights Apache-2.0 → royalty-free, EU-safe. No gate, no revenue cap.

## Requirements
- **Authors' base (README, conda):** python 3.9, `pytorch==2.1.2 torchvision==0.16.2
  torchaudio==2.1.2 pytorch-cuda=11.8`, conda xformers, then `pip install -r requirements.txt`
  and `bash install.sh`. This is the **oldest torch pin in our whole fleet** (2.1.2/cu118) —
  keep it venv-local (gotcha #3), it runs fine on newer drivers.
- **VRAM: NOT stated in the README** — unverified. 2 048-primitive PrimX + DiT-28-layer at fp16
  suggests it fits 16 GB, but treat the first pod run as the measurement.
- Repo: `https://github.com/3DTopia/3DTopia-XL` → `/workspace/repos/3DTopia-XL`
- **Compiled deps (install.sh, four!):** `dva/mvp/extensions/mvpraymarch` (make),
  `dva/mvp/extensions/utils` (make), `./simple-knn` (pip local), and `cubvh`
  (git clone ashawkey/cubvh + pip). All need nvcc + CUDA_HOME (universal gotcha #2).
- Weights (README wget, verbatim — two flat `.pt` files, into `./pretrained/`):
  ```
  wget https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_sview_dit_fp16.pt
  wget https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_vae_fp16.pt
  ```
  (flat files, no snapshot layout — this is why its HF download count undercounts, per the census
  popularity caveat).

## Working install recipe (anticipated — fill from the run)
```bash
export CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:$PATH
python -m venv /workspace/envs/3dtopiaxl --system-site-packages
source /workspace/envs/3dtopiaxl/bin/activate
pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu118
pip install xformers==0.0.23.post1 --index-url https://download.pytorch.org/whl/cu118
git clone --depth 1 https://github.com/3DTopia/3DTopia-XL /workspace/repos/3DTopia-XL
cd /workspace/repos/3DTopia-XL
pip install -r requirements.txt
bash install.sh                      # mvpraymarch + utils (make), simple-knn, cubvh — needs nvcc
pip install rembg onnxruntime omegaconf
mkdir -p pretrained
wget -nc -P pretrained https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_sview_dit_fp16.pt
wget -nc -P pretrained https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_vae_fp16.pt
```

## Run command (from the README — config-driven, no python API documented)
```bash
python inference.py ./configs/inference_dit.yml
```
`configs/inference_dit.yml`, the keys that matter (verbatim):
```yaml
checkpoint_path: ./pretrained/model_sview_dit_fp16.pt
vae_checkpoint_path: ./pretrained/model_vae_fp16.pt
output_dir: ${root_data_dir}/inference/${tag}
inference:
  input_dir: ./assets/examples
  ddim: 25
  cfg: 6
  seed: ${global_seed}        # default 42 — matches our contract out of the box
  precision: fp16
  export_glb: True
  fast_unwrap: False
  decimate: 100000
  mc_resolution: 256
  batch_size: 8192
  remesh: False
```
`inference.py` walks `input_dir`, does its **own rembg background removal + 0.85 foreground
resize**, seeds with `torch.manual_seed(seed)`, and writes per image:
`{output_dir}/inference_folder/{img_name}/pbr_mesh.glb` (+ `texture.jpg`,
`roughness_metallic.jpg`, diffusion-step previews).

Our batch driver: `deliverable/cloud_bundle/infer_3dtopiaxl.py` (DRAFT) — **wrapper pattern, not
in-process**: stages the manifest's missing items into a temp `input_dir`, writes a derived config
(absolute paths, seed 42), invokes the repo's own `inference.py` ONCE (single model load), then
collects each `pbr_mesh.glb` to `<key>.glb` with per-item OK/FAIL lines. Re-implementing the
PrimX/VAE/DiT load in-process from a README was judged higher-risk than driving the authors'
entry point.

## Anticipated issues (fill in the real chain after the run)
| # | Likely symptom | Likely cause | Likely fix |
|---|---|---|---|
| 1 | `make` fails in `dva/mvp/extensions/*` | nvcc missing / arch list | CUDA_HOME + PATH set; `TORCH_CUDA_ARCH_LIST=8.6` for A5000/4090 |
| 2 | cubvh build error | same compiled-dep class | `pip install --no-build-isolation` from the cloned dir |
| 3 | torch 2.1.2 wheel vs pod's newer base | venv `--system-site-packages` leaks newer torch | the venv-local pin must shadow base; if imports mix, rebuild venv **without** `--system-site-packages` |
| 4 | `output_dir: ${root_data_dir}/...` unresolved | OmegaConf interpolation, `root_data_dir` defined elsewhere in the yml | our driver overwrites `output_dir` with an absolute literal before writing the derived config |
| 5 | `{img_name}` folder naming mismatch (with/without extension) | README doesn't specify | driver globs `**/pbr_mesh.glb` and matches the parent dir against the key prefix |
| 6 | 25-step DDIM output too coarse on furniture | speed-tuned default | README: steps 25/50/100, "Robust with more steps" — re-run failures at `ddim: 100` |
| 7 | VRAM unknown → OOM on 24 GB | unstated requirement | fp16 default; lower `inference.batch_size` (it is the *point* batch, 8192) |
| 8 | GLB has PBR materials the scorer ignores | scorer is geometry-only | fine — geometry scored as usual; keep textures for the gallery |

## Verdict for the paper (anticipated)
The census-closer. Apache-2.0 end-to-end, the only PBR-native permissive generator, and the
fastest claimed inference of the trio (~5 s) — but a 2024-era model whose geometry the census
itself expects to trail TripoSG. If it (and the other two) lose on the research-10, we have the
documented negative result: *no untested permissive HF model beats the current stack.* Its PBR
GLBs still make the strongest gallery visuals for the report. Scores TBD.
