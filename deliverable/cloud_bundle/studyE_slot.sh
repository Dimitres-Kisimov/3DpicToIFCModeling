#!/bin/bash
# studyE_slot.sh — Study E: single vs multi-image, quantified. Rebuilds the
# trellis env from the attempt-5 proven recipe, runs run_multi_image on the
# 10 GT objects x 4 views, scores with the identical protocol. ~30 min GPU.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q ALL_ENGINES_FINAL $L 2>/dev/null; do sleep 300; done
while pgrep -f 'run[_]cloud_benchmark|infer[_]' > /dev/null; do sleep 180; done
mark SE_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
pip cache purge >/dev/null 2>&1

if [ ! -x /opt/envs/trellis/bin/python ]; then
  mark SE_TRELLIS_ENV_REBUILD
  mkdir -p /opt/envs/trellis && python3 -m venv /opt/envs/trellis
  ln -sfn /opt/envs/trellis /workspace/envs/trellis
  P=/opt/envs/trellis/bin/pip
  $P install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> /workspace/logs/se.log 2>&1
  $P install -q pillow imageio imageio-ffmpeg tqdm easydict opencv-python-headless scipy rembg \
    onnxruntime trimesh xatlas pyvista pymeshfix igraph transformers open3d plyfile safetensors ninja >> /workspace/logs/se.log 2>&1
  $P install -q spconv-cu121==2.3.8 >> /workspace/logs/se.log 2>&1
  $P install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> /workspace/logs/se.log 2>&1
  $P install -q xformers==0.0.28.post3 --index-url https://download.pytorch.org/whl/cu121 >> /workspace/logs/se.log 2>&1
  $P install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" >> /workspace/logs/se.log 2>&1
  echo /workspace/repos/TRELLIS > /opt/envs/trellis/lib/python3.12/site-packages/zz_trellis_repo.pth
fi
R=$(/opt/envs/trellis/bin/python -c "
import os; os.environ.setdefault('ATTN_BACKEND','sdpa'); os.environ.setdefault('SPARSE_ATTN_BACKEND','xformers'); os.environ.setdefault('SPCONV_ALGO','native')
from trellis.pipelines import TrellisImageTo3DPipeline
print('SE_IMPORT_OK')" 2>&1 | tail -1)
mark "SE_IMPORT $R"
echo "$R" | grep -q SE_IMPORT_OK || { mark SE_ABORT; exit 1; }

mark SE_RUN
/opt/envs/trellis/bin/python infer_trellis_mv.py studyE_manifest.json out/trellis_mv >> $L 2>&1
mark "SE_DONE n=$(ls out/trellis_mv/*.glb 2>/dev/null | wc -l)"
python score_all.py out >> $L 2>&1
mark "STUDY_E_COMPLETE — single vs multi-image scores in cloud_scores.csv (trellis vs trellis_mv rows)"
