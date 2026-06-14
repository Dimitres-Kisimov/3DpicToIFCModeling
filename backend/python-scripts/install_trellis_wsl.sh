#!/bin/bash
# Resume / restart the TRELLIS conda install inside WSL Ubuntu-22.04.
# Designed to run unattended in the background; logs go to
# /root/trellis_install.log so progress is monitorable from outside.
#
# Strip CRLF on first run if launched from /mnt/c via Windows-edited file.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

LOG=/root/trellis_install.log
exec > "$LOG" 2>&1

echo "=== TRELLIS install start: $(date) ==="
echo

echo "=== Stage 0: build prereqs ==="
apt-get update -qq
apt-get install -y -qq build-essential cmake git wget curl ca-certificates ninja-build
echo

echo "=== Stage 1: TRELLIS repo state ==="
cd /root/TRELLIS || { echo "FATAL no /root/TRELLIS"; exit 1; }
echo "TRELLIS HEAD: $(git rev-parse --short HEAD)"
git submodule update --init --recursive || true
echo

echo "=== Stage 2: pre-create conda env (TRELLIS setup.sh lacks -y on conda calls) ==="
source /opt/conda/etc/profile.d/conda.sh
if ! conda env list | grep -q "^trellis "; then
    conda create -n trellis python=3.10 -y
fi
conda activate trellis
# Pre-install pytorch with -y so the setup.sh --new-env block (which would
# rerun this without -y) is unnecessary.
conda install pytorch==2.4.0 torchvision==0.19.0 pytorch-cuda=11.8 \
    -c pytorch -c nvidia -y
echo

echo "=== Stage 3: run TRELLIS setup.sh inside env (WITHOUT --new-env) ==="
# --basic + --xformers: minimum for inference, fits 8 GB VRAM
# --spconv + --mipgaussian: required by SLAT decoders
# Excluded: --kaolin / --nvdiffrast / --diffoctreerast (build from source,
#           add 20+ min each; needed only for some renderers — can install
#           lazily later if a missing-module error surfaces).
# Excluded: --flash-attn (needs more VRAM than 8 GB)
# Pipe `yes` to auto-accept any apt/pip prompts inside setup.sh.
yes | bash setup.sh --basic --xformers --spconv --mipgaussian
SETUP_RV=$?
echo
echo "=== Stage 3 (setup.sh) exit code: $SETUP_RV ==="
echo

echo "=== Stage 4: verify ==="
conda activate trellis

python <<'PY'
import torch
print("torch:", torch.__version__, "cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("  device:", torch.cuda.get_device_name(0))
    print("  total VRAM:", torch.cuda.get_device_properties(0).total_memory // (1024 ** 2), "MiB")
PY

python <<'PY'
import sys
sys.path.insert(0, "/root/TRELLIS")
try:
    from trellis.pipelines import TrellisImageTo3DPipeline
    print("TrellisImageTo3DPipeline import: OK")
except Exception as e:
    print("TrellisImageTo3DPipeline import: FAIL —", e)
PY

echo
echo "=== TRELLIS install end: $(date) ==="
echo "DONE"
