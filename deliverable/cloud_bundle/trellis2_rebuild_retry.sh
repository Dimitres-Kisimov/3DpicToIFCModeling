#!/bin/bash
# trellis2_rebuild_retry.sh — TRELLIS 2.0 from zero once the DINOv3 gate opens.
# Its env was evicted for disk; this rebuilds it with every fix proven tonight:
# torch cu128 (pod toolkit is CUDA 12.8), no xformers/flash-attn (sdpa), CuMesh
# rebuilt from source (user-approved 2026-07-11), o-voxel rebuilt in-repo.
# Runs only when: DINOv3 downloadable AND campaign GPU work is finished.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark T2B_ARMED

until /workspace/envs/triposg/bin/python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(repo_id='facebook/dinov3-vitl16-pretrain-lvd1689m', filename='config.json')" > /dev/null 2>&1; do sleep 600; done
mark T2B_DINOV3_GRANTED
until grep -q CAMPAIGN_FULLY_COMPLETE $L 2>/dev/null; do sleep 300; done
while pgrep -f 'run[_]cloud_benchmark|infer[_]' > /dev/null; do sleep 300; done

mark T2B_SPACE_CLEAR
cd /workspace/cloud_bundle
for e in /opt/envs/sam3d /opt/envs/instantmesh; do
  [ -d "$e" ] && $e/bin/pip freeze > /workspace/$(basename $e)-freeze-final.txt 2>/dev/null && rm -rf "$e"
done
pip cache purge >/dev/null 2>&1
rm -rf $HUB/models--microsoft--TRELLIS-image-large 2>/dev/null   # trellis1 weights (re-downloadable; Study E re-fetches)
mark "T2B_FREE $(df -h / | tail -1 | awk '{print $4}')"

export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
mkdir -p /opt/envs/trellis2 && python3 -m venv /opt/envs/trellis2
ln -sfn /opt/envs/trellis2 /workspace/envs/trellis2
bash install_models.sh trellis2 >> /workspace/logs/t2b_install.log 2>&1
P=/opt/envs/trellis2/bin/pip
$P uninstall -q -y xformers flash-attn 2>/dev/null
$P install -q "torch==2.9.*" torchvision --index-url https://download.pytorch.org/whl/cu128 >> /workspace/logs/t2b_install.log 2>&1
rm -rf /workspace/tmp/CuMesh
git clone --quiet --recursive https://github.com/JeffreyXiang/CuMesh.git /workspace/tmp/CuMesh
$P install -q --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/tmp/CuMesh >> /workspace/logs/t2b_install.log 2>&1
$P install -q --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/repos/TRELLIS2/o-voxel >> /workspace/logs/t2b_install.log 2>&1

R=$(/opt/envs/trellis2/bin/python -c "
import sys; sys.path.insert(0, '/workspace/repos/TRELLIS2')
import os; os.environ.setdefault('ATTN_BACKEND', 'sdpa')
from trellis2.pipelines import Trellis2ImageTo3DPipeline
print('PIPELINE_OK')" 2>&1 | tail -1)
mark "T2B_IMPORT $R"
echo "$R" | grep -q PIPELINE_OK || { mark T2B_ABORT; exit 1; }

mark T2B_PREFLIGHT
rm -f out_preflight/trellis2/*.glb 2>/dev/null
python run_cloud_benchmark.py --models trellis2 --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/trellis2/*.glb 2>/dev/null | head -1)
if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then mark T2B_PREFLIGHT_FAIL; exit 1; fi
mark "T2B_PREFLIGHT_OK — FIRST TRELLIS 2.0 MESH IN PROJECT HISTORY"
python run_cloud_benchmark.py --models trellis2 >> $L 2>&1
python run_cloud_benchmark.py --models trellis2 --manifest bench170_manifest.json --out out170 >> $L 2>&1
mark "T2B_DONE r10=$(ls out/trellis2/*.glb 2>/dev/null | wc -l) s187=$(ls out170/trellis2/*.glb 2>/dev/null | wc -l)"
rm -rf $HUB/models--microsoft--TRELLIS.2-4B $HUB/models--facebook--dinov3* 2>/dev/null
python score_all.py out >> $L 2>&1
mark TRELLIS2_TRULY_COMPLETE
