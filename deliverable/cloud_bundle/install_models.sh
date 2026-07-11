#!/usr/bin/env bash
# install_models.sh — one-time setup of the generative 3D models on a RunPod pod.
# Adapted from cloud/compare_4way.sh (proven A40 recipes) for a BATCH benchmark on A100 80GB.
#
#   trellis     microsoft/TRELLIS-image-large   MIT   (proven API)
#   trellis2    microsoft/TRELLIS.2-4B          MIT   (newer; same pipeline class assumed — VERIFY)
#   triposg     VAST-AI/TripoSG                 MIT   (best-effort from repo docs)
#   instantmesh TencentARC/InstantMesh          Apache (proven CLI)
#   sam3d       facebook/sam-3d-objects         SAM Licence (best-effort; entrypoint may differ)
#
# Next-wave (Stage-7 licence audit 2026-07-11 — DRAFT recipes, not yet pod-proven; see manuals/):
#   direct3ds2  wushuang98/Direct3D-S2          MIT    (sparse-SDF geometry; torchsparse build)
#   step1x3d    stepfun-ai/Step1X-3D            Apache (textured 2-stage; heavy pinned deps)
#   hi3dgen     Stable-X/trellis-normal-v0-1    MIT    (repo is Stable-X/Stable3DGen — NOT /Hi3DGen)
#   partcrafter wgsxm/PartCrafter               MIT    (part-level meshes; avoid RMBG-1.4 masking)
#
# Census trio (docs/HF_CENSUS_2026-07.md, 2026-07-11 — DRAFT recipes, not yet pod-proven; see manuals/):
#   scenegen    haoningwu/SceneGen              MIT    (code = Mengmouxu/SceneGen; pulls facebook/VGGT-1B
#                                                       CC-BY-NC-4.0 — research benchmark ONLY)
#   cupid       hbb1/Cupid                      MIT    (code = cupid3d/Cupid; github.com/hbb1/Cupid is a stale stub)
#   3dtopiaxl   FrozenBurning/3DTopia-XL        Apache (PBR PrimX; torch 2.1.2/cu118 — oldest pin in the fleet)
#
# Usage:  bash install_models.sh                      # installs the default set: trellis trellis2 triposg
#         bash install_models.sh trellis triposg      # only these
#         bash install_models.sh all                  # all five proven-set models
#         bash install_models.sh nextwave             # the four Stage-7 draft models
#         bash install_models.sh censustrio           # the three census challengers (cheap 24GB pod)
#
# Design (from compare_4way.sh):
#   * NO `set -e` — one model failing must not abort the others.
#   * Each model gets its own venv (--system-site-packages shares the base torch).
#   * Idempotent: re-running skips already-cloned repos; safe to resume.
#   * Logs per model in /workspace/logs/install_<model>.log
set -u
ROOT=/workspace
REPOS="$ROOT/repos"; ENVS="$ROOT/envs"; LOGS="$ROOT/logs"
mkdir -p "$REPOS" "$ENVS" "$LOGS"

MODELS=("$@"); [ ${#MODELS[@]} -eq 0 ] && MODELS=(trellis trellis2 triposg)
[ "${MODELS[0]:-}" = "all" ] && MODELS=(trellis trellis2 triposg instantmesh sam3d)
[ "${MODELS[0]:-}" = "nextwave" ] && MODELS=(direct3ds2 step1x3d hi3dgen partcrafter)
[ "${MODELS[0]:-}" = "censustrio" ] && MODELS=(scenegen cupid 3dtopiaxl)

log(){ echo -e "\n=== [$(date +%H:%M:%S)] $* ==="; }
mkvenv(){ [ -d "$ENVS/$1" ] || python -m venv "$ENVS/$1" --system-site-packages; }

# A100 = sm_80; include 8.6 so the same bundle works on A40/L40 too.
export TORCH_CUDA_ARCH_LIST="8.0;8.6"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="$CUDA_HOME/bin:$PATH"
export PYOPENGL_PLATFORM=egl
export HF_HUB_ENABLE_HF_TRANSFER=0
# HF token (needed for SAM 3D gated weights) read from env HUGGING_FACE_HUB_TOKEN if set.

log "GPU + system build deps"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
apt-get update -y >"$LOGS/apt.log" 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git build-essential ninja-build pkg-config \
  libgl1 libglib2.0-0 libegl1 libgles2 libglvnd-dev >>"$LOGS/apt.log" 2>&1
pip install -q --upgrade pip >/dev/null 2>&1
# scoring deps live in BASE python (score_all.py runs here, not in a model venv)
pip install -q trimesh scipy numpy pillow rembg onnxruntime >"$LOGS/install_base.log" 2>&1

has(){ for m in "${MODELS[@]}"; do [ "$m" = "$1" ] && return 0; done; return 1; }

# ---------------------------------------------------------------- TRELLIS ----
install_trellis(){
  local V="$ENVS/trellis"; log "install: trellis (TRELLIS-image-large)"
  { mkvenv trellis; source "$V/bin/activate"
    [ -d "$REPOS/TRELLIS" ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS "$REPOS/TRELLIS"
    cd "$REPOS/TRELLIS"
    pip install -q pillow imageio imageio-ffmpeg trimesh numpy scipy easydict \
      opencv-python-headless tqdm einops omegaconf rembg onnxruntime
    pip install -q xformers || true
    pip install -q flash-attn --no-build-isolation || true
    # spconv must match the pod's CUDA: cu120 for CUDA-12 images (RunPod PyTorch 2.8), cu118 otherwise.
    pip install -q spconv-cu120 || pip install -q spconv-cu118 || true
    pip install -q git+https://github.com/NVlabs/nvdiffrast.git || true
    pip install -q git+https://github.com/JeffreyXiang/diffoctreerast.git || true
    pip install -q utils3d || true
    # warm the weights so the timed run is inference-only
    python -c "from trellis.pipelines import TrellisImageTo3DPipeline as P; P.from_pretrained('microsoft/TRELLIS-image-large')" || true
    deactivate
  } >"$LOGS/install_trellis.log" 2>&1
  echo "trellis install done -> $LOGS/install_trellis.log"
}

install_trellis2(){
  local V="$ENVS/trellis2"; log "install: trellis2 (TRELLIS.2-4B — SEPARATE repo, see manuals/TRELLIS2.md)"
  { mkvenv trellis2; source "$V/bin/activate"
    # TRELLIS.2 is NOT the v1 codebase: repo microsoft/TRELLIS.2, package `trellis2`,
    # O-Voxel representation, `o_voxel` exporter. The v1 pipeline can't load .2-4B.
    [ -d "$REPOS/TRELLIS2" ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS.2 "$REPOS/TRELLIS2"
    cd "$REPOS/TRELLIS2"
    # follow the repo's own setup first; fall back to the v1 lesson stack
    bash setup.sh --basic 2>/dev/null || true
    pip install -q pillow imageio imageio-ffmpeg trimesh numpy scipy easydict \
      opencv-python-headless tqdm einops omegaconf rembg onnxruntime transformers open3d
    pip install -q --no-deps xformers || true                       # v1 lesson #1
    pip install -q flash-attn --no-build-isolation || true          # v1 lesson #6
    pip install -q spconv-cu120 || pip install -q spconv-cu118 || true
    pip install -q git+https://github.com/NVlabs/nvdiffrast.git --no-build-isolation || true
    pip install -q git+https://github.com/JeffreyXiang/diffoctreerast.git --no-build-isolation || true
    pip install -q -e . || true                                     # the trellis2 package itself
    pip install -q o_voxel || pip install -q -e ./o_voxel || true   # the exporter
    python -c "from huggingface_hub import snapshot_download; snapshot_download('microsoft/TRELLIS.2-4B')" || true
    python -c "import sys; sys.path.insert(0,'.'); from trellis2.pipelines import Trellis2ImageTo3DPipeline; print('trellis2 import OK')" \
      || echo 'NOTE: trellis2 import failed — read the repo README + manuals/TRELLIS2.md anticipated-issues table'
    deactivate
  } >"$LOGS/install_trellis2.log" 2>&1
  echo "trellis2 install done -> $LOGS/install_trellis2.log"
}

install_sf3d(){
  local V="$ENVS/sf3d"; log "install: sf3d (Stable Fast 3D — benchmark-only, Stability Community License)"
  { mkvenv sf3d; source "$V/bin/activate"
    [ -d "$REPOS/stable-fast-3d" ] || git clone --depth 1 https://github.com/Stability-AI/stable-fast-3d "$REPOS/stable-fast-3d"
    cd "$REPOS/stable-fast-3d"
    pip install -q -r requirements.txt || true
    pip install -q rembg onnxruntime
    # weights are gated on HF — accept the licence on the model page with this account first
    python -c "from huggingface_hub import snapshot_download; snapshot_download('stabilityai/stable-fast-3d')" || \
      echo 'NOTE: accept the licence at hf.co/stabilityai/stable-fast-3d, then huggingface-cli login'
    deactivate
  } >"$LOGS/install_sf3d.log" 2>&1
  echo "sf3d install done -> $LOGS/install_sf3d.log"
}

# ---------------------------------------------------------------- TripoSG ----
install_triposg(){
  local V="$ENVS/triposg"; log "install: triposg (VAST-AI/TripoSG)"
  { mkvenv triposg; source "$V/bin/activate"
    [ -d "$REPOS/TripoSG" ] || git clone --depth 1 https://github.com/VAST-AI-Research/TripoSG "$REPOS/TripoSG"
    cd "$REPOS/TripoSG"
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121 || true
    pip install -q diffusers transformers einops trimesh numpy scipy pillow \
      huggingface_hub omegaconf rembg onnxruntime opencv-python-headless || true
    [ -f requirements.txt ] && pip install -q -r requirements.txt || true
    python -c "from huggingface_hub import snapshot_download; snapshot_download('VAST-AI/TripoSG')" || true
    deactivate
  } >"$LOGS/install_triposg.log" 2>&1
  echo "triposg install done -> $LOGS/install_triposg.log"
}

# ------------------------------------------------------------ InstantMesh ----
install_instantmesh(){
  local V="$ENVS/instantmesh"; log "install: instantmesh"
  { mkvenv instantmesh; source "$V/bin/activate"
    pip install -q transformers==4.40.0 diffusers==0.27.2 huggingface_hub==0.23.0 \
      pytorch-lightning==2.1.2 einops omegaconf trimesh rembg onnxruntime \
      imageio imageio-ffmpeg pillow numpy xatlas plyfile || true
    pip install -q git+https://github.com/NVlabs/nvdiffrast.git || true
    [ -d "$REPOS/InstantMesh" ] || git clone --depth 1 https://github.com/TencentARC/InstantMesh "$REPOS/InstantMesh"
    deactivate
  } >"$LOGS/install_instantmesh.log" 2>&1
  echo "instantmesh install done -> $LOGS/install_instantmesh.log"
}

# ---------------------------------------------------------------- SAM 3D ----
install_sam3d(){
  local V="$ENVS/sam3d"; log "install: sam3d (gated — needs HUGGING_FACE_HUB_TOKEN)"
  { mkvenv sam3d; source "$V/bin/activate"
    pip install -q "git+https://github.com/facebookresearch/pytorch3d.git@stable" || true
    [ -d "$REPOS/SAM3D" ] || git clone --depth 1 https://github.com/facebookresearch/sam-3d-objects "$REPOS/SAM3D"
    cd "$REPOS/SAM3D"
    pip install -q -e . || pip install -q -r requirements.txt || true
    deactivate
  } >"$LOGS/install_sam3d.log" 2>&1
  echo "sam3d install done -> $LOGS/install_sam3d.log"
}

# ============== NEXT-WAVE (Stage-7 audit 2026-07-11) — DRAFT, not yet pod-proven ==============

# ------------------------------------------------------------- Direct3D-S2 ----
install_direct3ds2(){
  local V="$ENVS/direct3ds2"; log "install: direct3ds2 (DreamTechAI/Direct3D-S2 — DRAFT, manuals/DIRECT3D_S2.md)"
  { mkvenv direct3ds2; source "$V/bin/activate"
    # authors' tested base is torch 2.5.1+cu121 (SAM3D lesson: official base > improvised)
    pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 || true
    # torchsparse builds from source and needs the sparsehash headers first
    DEBIAN_FRONTEND=noninteractive apt-get install -y libsparsehash-dev >>"$LOGS/apt.log" 2>&1 || true
    [ -d "$REPOS/torchsparse" ] || git clone --depth 1 https://github.com/mit-han-lab/torchsparse "$REPOS/torchsparse"
    pip install -q --no-build-isolation "$REPOS/torchsparse" || true
    [ -d "$REPOS/Direct3D-S2" ] || git clone --depth 1 https://github.com/DreamTechAI/Direct3D-S2 "$REPOS/Direct3D-S2"
    cd "$REPOS/Direct3D-S2"
    # requirements.txt contains flash-attn AND a local path (third_party/voxelize) —
    # install the pure-python bulk explicitly, compiled bits with --no-build-isolation:
    pip install -q scikit-image trimesh omegaconf tqdm huggingface_hub einops numpy \
      "transformers==4.40.2" diffusers "triton==3.1.0" pymeshfix pyvista igraph \
      rembg onnxruntime || true
    pip install -q "git+https://github.com/EasternJournalist/utils3d.git" || true
    pip install -q --no-build-isolation flash-attn || true          # gotcha #6 — sdpa fallback UNVERIFIED
    pip install -q --no-build-isolation ./third_party/voxelize || true
    pip install -q -e . --no-deps || true
    python -c "from huggingface_hub import snapshot_download; snapshot_download('wushuang98/Direct3D-S2')" || true
    deactivate
  } >"$LOGS/install_direct3ds2.log" 2>&1
  echo "direct3ds2 install done -> $LOGS/install_direct3ds2.log"
}

# --------------------------------------------------------------- Step1X-3D ----
install_step1x3d(){
  local V="$ENVS/step1x3d"; log "install: step1x3d (stepfun-ai/Step1X-3D — DRAFT, manuals/STEP1X_3D.md)"
  { mkvenv step1x3d; source "$V/bin/activate"
    [ -d "$REPOS/Step1X-3D" ] || git clone --depth 1 https://github.com/stepfun-ai/Step1X-3D "$REPOS/Step1X-3D"
    cd "$REPOS/Step1X-3D"
    pip install -q torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124 || true
    pip install -q -r requirements.txt || true         # LONG: builds nvdiffrast + pytorch3d from git
    pip install -q torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu124.html || true
    pip install -q kaolin==0.17.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu124.html || true
    # texture-stage compiled extensions (geometry-only benchmark works without them):
    ( cd step1x3d_texture/custom_rasterizer && python setup.py install ) || true
    ( cd step1x3d_texture/differentiable_renderer && python setup.py install ) || true
    # geometry weights only (the full repo also carries Label + Texture subfolders):
    python -c "from huggingface_hub import snapshot_download; snapshot_download('stepfun-ai/Step1X-3D', allow_patterns=['Step1X-3D-Geometry-1300m/*'])" || true
    deactivate
  } >"$LOGS/install_step1x3d.log" 2>&1
  echo "step1x3d install done -> $LOGS/install_step1x3d.log"
}

# ------------------------------------------------- Hi3DGen (Stable3DGen) ----
install_hi3dgen(){
  local V="$ENVS/hi3dgen"; log "install: hi3dgen (Stable-X/Stable3DGen — DRAFT, manuals/HI3DGEN.md)"
  { mkvenv hi3dgen; source "$V/bin/activate"
    # NAMING TRAP: the repo is Stable3DGen — github.com/Stable-X/Hi3DGen does not exist.
    [ -d "$REPOS/Stable3DGen" ] || git clone --recursive https://github.com/Stable-X/Stable3DGen "$REPOS/Stable3DGen"
    cd "$REPOS/Stable3DGen"
    # repo pins its OWN torch (2.4.0) — keep it venv-local, never let it bump (gotcha #3)
    pip install -q torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124 || true
    pip install -q spconv-cu124==2.3.6 || pip install -q spconv-cu120==2.3.6 || true
    pip install -q --no-deps xformers==0.0.27.post2 || true         # matched to torch 2.4.0
    pip install -q -r requirements.txt || true
    pip install -q rembg onnxruntime || true
    # weights where app.py expects them (weights/<name>) — pipeline loads from the LOCAL folder
    python -c "
from huggingface_hub import snapshot_download
import os
for rid in ['Stable-X/trellis-normal-v0-1','Stable-X/yoso-normal-v1-8-1','ZhengPeng7/BiRefNet']:
    snapshot_download(repo_id=rid, local_dir=os.path.join('weights', rid.split('/')[-1]))
" || true
    deactivate
  } >"$LOGS/install_hi3dgen.log" 2>&1
  echo "hi3dgen install done -> $LOGS/install_hi3dgen.log"
}

# -------------------------------------------------------------- PartCrafter ----
install_partcrafter(){
  local V="$ENVS/partcrafter"; log "install: partcrafter (wgsxm/PartCrafter — DRAFT, manuals/PARTCRAFTER.md)"
  { mkvenv partcrafter; source "$V/bin/activate"
    [ -d "$REPOS/PartCrafter" ] || git clone --depth 1 https://github.com/wgsxm/PartCrafter "$REPOS/PartCrafter"
    cd "$REPOS/PartCrafter"
    pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 || true
    pip install -q torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu124.html || true
    pip install -q -r settings/requirements.txt || true   # deepspeed/wandb/google-genai may fail soft — training-only
    pip install -q rembg onnxruntime || true               # our masking (RMBG-1.4 is license:other — do NOT use)
    DEBIAN_FRONTEND=noninteractive apt-get install -y libegl1 libgl1-mesa-dev >>"$LOGS/apt.log" 2>&1 || true
    python -c "from huggingface_hub import snapshot_download; snapshot_download('wgsxm/PartCrafter')" || true
    deactivate
  } >"$LOGS/install_partcrafter.log" 2>&1
  echo "partcrafter install done -> $LOGS/install_partcrafter.log"
}

# ============== CENSUS TRIO (docs/HF_CENSUS_2026-07.md, 2026-07-11) — DRAFT, not yet pod-proven ==============

# ---------------------------------------------------------------- SceneGen ----
install_scenegen(){
  local V="$ENVS/scenegen"; log "install: scenegen (Mengmouxu/SceneGen — DRAFT, manuals/SCENEGEN.md)"
  { mkvenv scenegen; source "$V/bin/activate"
    # NAMING TRAP: code = Mengmouxu/SceneGen (haoningwu3639/SceneGen 404s); weights = haoningwu/SceneGen.
    [ -d "$REPOS/SceneGen" ] || git clone --recurse-submodules https://github.com/Mengmouxu/SceneGen "$REPOS/SceneGen"
    cd "$REPOS/SceneGen"
    # TRELLIS-family setup.sh — README uses `--new-env` (conda) + `--demo` (gradio); drop both in the venv:
    . ./setup.sh --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast || true
    pip install -q rembg onnxruntime || true
    mkdir -p checkpoints
    # ⚠️ facebook/VGGT-1B is CC-BY-NC-4.0 (HF API 2026-07-11) — research benchmark ONLY,
    # never ship; see manuals/SCENEGEN.md licence section.
    python -c "
from huggingface_hub import snapshot_download
snapshot_download('haoningwu/SceneGen',        local_dir='checkpoints/scenegen')
snapshot_download('facebook/sam2-hiera-large', local_dir='checkpoints/sam2-hiera-large')
snapshot_download('facebook/VGGT-1B',          local_dir='checkpoints/VGGT-1B')
" || true
    deactivate
  } >"$LOGS/install_scenegen.log" 2>&1
  echo "scenegen install done -> $LOGS/install_scenegen.log"
}

# ------------------------------------------------------------------- Cupid ----
install_cupid(){
  local V="$ENVS/cupid"; log "install: cupid (cupid3d/Cupid — DRAFT, manuals/CUPID.md)"
  { mkvenv cupid; source "$V/bin/activate"
    # NAMING TRAP: code = cupid3d/Cupid (hbb1/Cupid on GitHub is a stale stub); weights = hbb1/Cupid on HF.
    # README default: torch 2.4.0 + cu118, CUDA 11.8/12.2 tested — cu124 wheel on our CUDA-12 pods (Hi3DGen lesson).
    pip install -q torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu124 || true
    [ -d "$REPOS/Cupid" ] || git clone --recurse-submodules https://github.com/cupid3d/Cupid "$REPOS/Cupid"
    cd "$REPOS/Cupid"
    # TRELLIS-family setup.sh, two extra flags vs SceneGen (--pytorch3d --moge); drop --new-env (conda):
    . ./setup.sh --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast --pytorch3d --moge || true
    pip install -q rembg onnxruntime || true
    python -c "from huggingface_hub import snapshot_download; snapshot_download('hbb1/Cupid')" || true
    deactivate
  } >"$LOGS/install_cupid.log" 2>&1
  echo "cupid install done -> $LOGS/install_cupid.log"
}

# -------------------------------------------------------------- 3DTopia-XL ----
install_3dtopiaxl(){
  local V="$ENVS/3dtopiaxl"; log "install: 3dtopiaxl (3DTopia/3DTopia-XL — DRAFT, manuals/TOPIA_XL.md)"
  { mkvenv 3dtopiaxl; source "$V/bin/activate"
    # authors' base is python 3.9 + torch 2.1.2 + cu118 (conda README) — venv equivalent, keep it LOCAL:
    pip install -q torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu118 || true
    pip install -q xformers==0.0.23.post1 --index-url https://download.pytorch.org/whl/cu118 || pip install -q xformers || true
    [ -d "$REPOS/3DTopia-XL" ] || git clone --depth 1 https://github.com/3DTopia/3DTopia-XL "$REPOS/3DTopia-XL"
    cd "$REPOS/3DTopia-XL"
    pip install -q -r requirements.txt || true
    # install.sh compiles mvpraymarch + utils (make) + simple-knn + cubvh — needs nvcc + CUDA_HOME:
    bash install.sh || true
    pip install -q rembg onnxruntime omegaconf || true
    # weights are two flat .pt files (no snapshot layout) — README wget, into ./pretrained/:
    mkdir -p pretrained
    wget -q -nc -P pretrained https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_sview_dit_fp16.pt || true
    wget -q -nc -P pretrained https://huggingface.co/FrozenBurning/3DTopia-XL/resolve/main/model_vae_fp16.pt || true
    deactivate
  } >"$LOGS/install_3dtopiaxl.log" 2>&1
  echo "3dtopiaxl install done -> $LOGS/install_3dtopiaxl.log"
}

# pre-clone repos SHARED across venvs first, so parallel installs don't race on git clone
if has trellis; then
  [ -d "$REPOS/TRELLIS" ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS "$REPOS/TRELLIS" >/dev/null 2>&1
fi
if has trellis2; then
  [ -d "$REPOS/TRELLIS2" ] || git clone --recurse-submodules https://github.com/microsoft/TRELLIS.2 "$REPOS/TRELLIS2" >/dev/null 2>&1
fi

log "installing ${#MODELS[@]} models IN PARALLEL (money-no-object / min-time mode) — watch logs/install_*.log"
pids=()
for m in "${MODELS[@]}"; do
  case "$m" in
    trellis) install_trellis & pids+=($!);;
    trellis2) install_trellis2 & pids+=($!);;
    triposg) install_triposg & pids+=($!);;
    instantmesh) install_instantmesh & pids+=($!);;
    sam3d) install_sam3d & pids+=($!);;
    sf3d) install_sf3d & pids+=($!);;
    direct3ds2) install_direct3ds2 & pids+=($!);;    # DRAFT — not yet pod-proven
    step1x3d) install_step1x3d & pids+=($!);;        # DRAFT — not yet pod-proven
    hi3dgen) install_hi3dgen & pids+=($!);;          # DRAFT — not yet pod-proven
    partcrafter) install_partcrafter & pids+=($!);;  # DRAFT — not yet pod-proven
    scenegen) install_scenegen & pids+=($!);;        # DRAFT census trio — VGGT-1B is NC, benchmark only
    cupid) install_cupid & pids+=($!);;              # DRAFT census trio
    3dtopiaxl) install_3dtopiaxl & pids+=($!);;      # DRAFT census trio
    *) echo "unknown model: $m";;
  esac
done
echo "parallel install PIDs: ${pids[*]} — waiting for all to finish ..."
wait
log "INSTALL COMPLETE for: ${MODELS[*]}  — now: python run_cloud_benchmark.py --models ${MODELS[*]// /,} --parallel 5"
