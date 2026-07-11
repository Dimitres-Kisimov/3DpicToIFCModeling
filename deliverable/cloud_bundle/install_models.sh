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
# Usage:  bash install_models.sh                      # installs the default set: trellis trellis2 triposg
#         bash install_models.sh trellis triposg      # only these
#         bash install_models.sh all                  # all five
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
    *) echo "unknown model: $m";;
  esac
done
echo "parallel install PIDs: ${pids[*]} — waiting for all to finish ..."
wait
log "INSTALL COMPLETE for: ${MODELS[*]}  — now: python run_cloud_benchmark.py --models ${MODELS[*]// /,} --parallel 5"
