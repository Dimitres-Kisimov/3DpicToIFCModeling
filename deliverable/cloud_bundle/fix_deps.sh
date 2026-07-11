#!/bin/bash
# fix_deps.sh — chase missing modules per env until each model's import chain
# passes, then relaunch queue3. The truncated-env aftermath left each env
# missing a different dependency subset; this loops import -> parse missing
# module -> install -> retry (max 18 rounds), with special cases for CUDA builds.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark FD_START

chase(){  # $1 env-python  $2 name  $3 import-test-file
  for i in $(seq 1 18); do
    ERR=$($1 $3 2>&1)
    if echo "$ERR" | grep -q IMPORT_OK; then mark "FD_${2}_OK iter=$i"; return 0; fi
    MOD=$(echo "$ERR" | grep -oP "No module named '\K[^']+" | tail -1 | cut -d. -f1)
    if [ -z "$MOD" ]; then
      mark "FD_${2}_STUCK iter=$i: $(echo "$ERR" | tail -2 | tr '\n' ' ' | cut -c1-160)"
      return 1
    fi
    mark "FD_${2}_MISSING $MOD"
    case $MOD in
      torchvision) $1 -m pip install -q torchvision --index-url https://download.pytorch.org/whl/cu130 ;;
      torch)       mark "FD_${2}_NEEDS_TORCH — not auto-installing"; return 1 ;;
      nvdiffrast)  $1 -m pip install -q ninja; CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 \
                   $1 -m pip install -q --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast" ;;
      flash_attn)  mark "FD_${2}_FLASHATTN — should be sdpa-pinned, not installing"; return 1 ;;
      diso)        CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 $1 -m pip install -q --no-build-isolation diso ;;
      cv2)         $1 -m pip install -q opencv-python-headless ;;
      *)           $1 -m pip install -q "$MOD" || { mark "FD_${2}_PIPFAIL $MOD"; return 1; } ;;
    esac
  done
  mark "FD_${2}_MAXITER"; return 1
}

cat > /tmp/t_trellis.py <<'PY'
import os
os.environ.setdefault('ATTN_BACKEND', 'sdpa'); os.environ.setdefault('SPCONV_ALGO', 'native')
from trellis.pipelines import TrellisImageTo3DPipeline
print('IMPORT_OK')
PY
cat > /tmp/t_im.py <<'PY'
import sys; sys.path.insert(0, '/workspace/repos/InstantMesh')
from src.utils.mesh_util import save_obj
print('IMPORT_OK')
PY
cat > /tmp/t_sf3d.py <<'PY'
import sys; sys.path.insert(0, '/workspace/repos/stable-fast-3d')
from sf3d.system import SF3D
print('IMPORT_OK')
PY
cat > /tmp/t_sam3d.py <<'PY'
import os, sys
os.environ.setdefault('CONDA_PREFIX', '/usr/local/cuda'); os.environ.setdefault('LIDRA_SKIP_INIT', 'true')
os.environ['SPARSE_ATTN_BACKEND'] = 'sdpa'; os.environ['ATTN_BACKEND'] = 'sdpa'
sys.path.insert(0, '/workspace/repos/SAM3D'); sys.path.insert(0, '/workspace/repos/SAM3D/notebook')
try:
    import utils3d.numpy as u
    for f in ('depth_edge', 'normals_edge', 'points_to_normals', 'image_uv', 'image_mesh'):
        if not hasattr(u, f): setattr(u, f, lambda *a, **k: None)
except ModuleNotFoundError:
    raise
from inference import Inference
print('IMPORT_OK')
PY

chase /workspace/envs/trellis/bin/python TRELLIS /tmp/t_trellis.py
chase /opt/envs/instantmesh/bin/python IM /tmp/t_im.py
chase /workspace/envs/sf3d/bin/python SF3D /tmp/t_sf3d.py
chase /opt/envs/sam3d/bin/python SAM3D /tmp/t_sam3d.py
mark FD_ALL_DONE

# let a still-running mask precompute finish, then relaunch the verified queue
while pgrep -f 'precompute[_]masks' > /dev/null; do sleep 20; done
setsid nohup bash /workspace/queue3_verified.sh > /dev/null 2>&1 < /dev/null &
mark Q3_RELAUNCHED
