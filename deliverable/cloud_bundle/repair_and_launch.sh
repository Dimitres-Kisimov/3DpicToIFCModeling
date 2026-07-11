#!/bin/bash
# repair_and_launch.sh — one-time env repairs after the 2026-07-11 disk incident,
# then launches queue3_verified.sh. All markers -> queue_rest.log (monitored).
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark R_START

# 0. remove the fabricated sam3d outputs (identical placeholder copies of a repo asset)
rm -rf /workspace/cloud_bundle/out/sam3d /workspace/cloud_bundle/out170/sam3d
mark R_FAKES_REMOVED

# 1. trellis: the rebuilt env has the deps but not the repo package — put repo on its path
echo /workspace/repos/TRELLIS > /opt/envs/trellis/lib/python3.12/site-packages/zz_trellis_repo.pth
if /workspace/envs/trellis/bin/python - <<'PY'
import os
os.environ.setdefault('ATTN_BACKEND', 'sdpa')
os.environ.setdefault('SPCONV_ALGO', 'native')
from trellis.pipelines import TrellisImageTo3DPipeline
print('trellis import ok')
PY
then mark R_TRELLIS_IMPORT_OK; else mark "R_TRELLIS_IMPORT_FAIL see logs"; fi

# 2. instantmesh: truncated env lost cv2 (and maybe friends)
/opt/envs/instantmesh/bin/pip install -q opencv-python-headless >> $L 2>&1
if (cd /workspace/repos/InstantMesh && /opt/envs/instantmesh/bin/python -c "from src.utils.mesh_util import save_obj"); then
  mark R_INSTANTMESH_IMPORT_OK
else
  mark "R_INSTANTMESH_IMPORT_FAIL see logs"
fi

# 3. sam3d: sdpa hard pin (manual fix #5) + the pure-python dep batch (manual fix #7/#8)
F=/workspace/repos/SAM3D/sam3d_objects/model/backbone/tdfy_dit/modules/sparse/__init__.py
grep -q 'ATTN = "sdpa"' "$F" || sed -i '/__from_env()/a ATTN = "sdpa"' "$F"
/opt/envs/sam3d/bin/pip install -q loguru timm==0.9.16 spconv-cu121==2.3.8 open3d trimesh \
  optree==0.14.1 astor rootutils randomname opencv-python==4.9.0.80 roma==1.5.1 einops \
  xatlas==0.0.9 Rtree==1.3.0 omegaconf "scikit-image==0.23.1" "tifffile==2024.8.30" \
  "plyfile==1.0.3" "lightning==2.3.3" pyvista "pymeshfix==0.17.0" igraph "numpy==1.26.4" >> $L 2>&1
/opt/envs/sam3d/bin/pip install -q "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b" >> $L 2>&1
/opt/envs/sam3d/bin/pip install -q "numpy==1.26.4" >> $L 2>&1   # re-pin (manual numpy war, fix #8)
mark R_SAM3D_DEPS_DONE

# 4. rembg into the triposg env — mask precompute for internet photos (sam3d needs masks)
/workspace/envs/triposg/bin/pip install -q rembg onnxruntime >> $L 2>&1
mark R_REMBG_DONE

mark R_ALL_DONE
setsid nohup bash /workspace/queue3_verified.sh > /dev/null 2>&1 < /dev/null &
mark Q3_LAUNCHED
