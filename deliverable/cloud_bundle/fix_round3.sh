#!/bin/bash
# fix_round3.sh — final targeted env repairs, then relaunch the gated queue.
# sam3d: + kaolin (wheel exists for its torch 2.5.1+cu121) ; trellis: downgrade
# torch 2.13+cu130 -> 2.5.1+cu121 (only stack with a kaolin wheel) ; sf3d: build
# vendored CUDA/C++ extensions with no-build-isolation + CUDA env.
L=/workspace/logs/queue_rest.log
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark FR3_START
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0

/opt/envs/sam3d/bin/pip install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1
/opt/envs/sam3d/bin/pip install -q 'numpy==1.26.4' >> $L 2>&1
R=$(/opt/envs/sam3d/bin/python /tmp/t_sam3d.py 2>&1 | tail -1); mark "FR3_SAM3D $R"

/workspace/envs/trellis/bin/pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> $L 2>&1
/workspace/envs/trellis/bin/pip uninstall -q -y xformers flash-attn 2>/dev/null
/workspace/envs/trellis/bin/pip install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1
R=$(/workspace/envs/trellis/bin/python /tmp/t_trellis.py 2>&1 | tail -1); mark "FR3_TRELLIS $R"

cd /workspace/repos/stable-fast-3d
/workspace/envs/sf3d/bin/pip install -q --no-build-isolation ./uv_unwrapper >> $L 2>&1
/workspace/envs/sf3d/bin/pip install -q --no-build-isolation ./texture_baker >> $L 2>&1
R=$(/workspace/envs/sf3d/bin/python /tmp/t_sf3d.py 2>&1 | tail -1); mark "FR3_SF3D $R"

# instantmesh already verified. Relaunch the gated queue whatever the outcome —
# preflights skip anything still broken instead of fabricating results.
mark FR3_DONE_RELAUNCHING
setsid nohup bash /workspace/queue3_verified.sh > /dev/null 2>&1 < /dev/null &
