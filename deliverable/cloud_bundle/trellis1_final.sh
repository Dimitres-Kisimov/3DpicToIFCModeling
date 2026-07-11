#!/bin/bash
# trellis1_final.sh — the campaign's last slot: TRELLIS 1.0 rebuilt WITH
# nvdiffrast (its infer path hard-imports it; benchmark-tier use, same
# precedent as InstantMesh), gate, 10+187 batch, final rescore — then the env
# is KEPT for Study E (run_multi_image). Chained after SAM3D_CAMPAIGN_COMPLETE.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q SAM3D_CAMPAIGN_COMPLETE $L 2>/dev/null; do sleep 120; done
mark T1F_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
pip cache purge >/dev/null 2>&1

mkdir -p /opt/envs/trellis && python3 -m venv /opt/envs/trellis
ln -sfn /opt/envs/trellis /workspace/envs/trellis
P=/opt/envs/trellis/bin/pip
$P install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> /workspace/logs/t1f.log 2>&1
$P install -q pillow imageio imageio-ffmpeg tqdm easydict opencv-python-headless scipy rembg \
  onnxruntime trimesh xatlas pyvista pymeshfix igraph transformers open3d plyfile safetensors ninja >> /workspace/logs/t1f.log 2>&1
$P install -q spconv-cu121==2.3.8 >> /workspace/logs/t1f.log 2>&1
$P install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> /workspace/logs/t1f.log 2>&1
$P install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" >> /workspace/logs/t1f.log 2>&1
$P install -q --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast" >> /workspace/logs/t1f.log 2>&1
echo /workspace/repos/TRELLIS > /opt/envs/trellis/lib/python3.12/site-packages/zz_trellis_repo.pth

R=$(/opt/envs/trellis/bin/python -c "
import os; os.environ.setdefault('ATTN_BACKEND','sdpa'); os.environ.setdefault('SPCONV_ALGO','native')
from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils
print('T1_IMPORT_OK')" 2>&1 | tail -1)
mark "T1F_IMPORT $R"
echo "$R" | grep -q T1_IMPORT_OK || { mark T1F_ABORT; exit 1; }

mark T1F_PREFLIGHT
rm -f out_preflight/trellis/*.glb 2>/dev/null
python run_cloud_benchmark.py --models trellis --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/trellis/*.glb 2>/dev/null | head -1)
if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
  mark "T1F_PREFLIGHT_FAIL — see logs/trellis.log"; exit 1
fi
mark T1F_PREFLIGHT_OK
python run_cloud_benchmark.py --models trellis >> $L 2>&1
python run_cloud_benchmark.py --models trellis --manifest bench170_manifest.json --out out170 >> $L 2>&1
mark "T1F_DONE r10=$(ls out/trellis/*.glb 2>/dev/null | wc -l) s187=$(ls out170/trellis/*.glb 2>/dev/null | wc -l)"

python score_all.py out >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
# env + weights KEPT: Study E (run_multi_image) uses them next
mark "CAMPAIGN_FULLY_COMPLETE — all engines attempted; download when ready"
