#!/bin/bash
# t2_torch_fix.sh — trellis2 env: swap torch cu130 -> cu128 (pod toolkit is CUDA
# 12.8; cu130 torch can't compile extensions here), drop the now-ABI-orphaned
# xformers/flash_attn (sdpa fallback is the pod-proven path), rebuild CuMesh
# (user-approved source) and o-voxel (part of the TRELLIS.2 repo) against the
# new torch, then import-gate. CPU-only; safe alongside a GPU batch.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark Q4_T2FIX_START
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
P=/opt/envs/trellis2/bin/pip

$P uninstall -q -y xformers flash-attn 2>/dev/null
$P install -q "torch==2.9.*" torchvision --index-url https://download.pytorch.org/whl/cu128 >> /workspace/logs/t2_torch_fix.log 2>&1
V=$(/opt/envs/trellis2/bin/python -c "import torch; print(torch.__version__)" 2>&1 | tail -1)
mark "Q4_T2FIX_TORCH $V"

$P install -q --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/tmp/CuMesh >> /workspace/logs/t2_torch_fix.log 2>&1
R=$(/opt/envs/trellis2/bin/python -c "import cumesh; print('OK')" 2>&1 | tail -1)
mark "Q4_T2FIX_CUMESH $R"

$P install -q --no-build-isolation --force-reinstall --no-cache-dir --no-deps /workspace/repos/TRELLIS2/o-voxel >> /workspace/logs/t2_torch_fix.log 2>&1
R=$(/opt/envs/trellis2/bin/python -c "import o_voxel; print('OK')" 2>&1 | tail -1)
mark "Q4_T2FIX_OVOXEL $R"

R=$(/opt/envs/trellis2/bin/python -c "
import sys; sys.path.insert(0, '/workspace/repos/TRELLIS2')
import os; os.environ.setdefault('ATTN_BACKEND', 'sdpa')
from trellis2.pipelines import Trellis2ImageTo3DPipeline
print('PIPELINE_OK')" 2>&1 | tail -1)
mark "Q4_T2FIX_PIPELINE $R"
