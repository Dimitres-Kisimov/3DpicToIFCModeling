#!/bin/bash
# Sets up TRELLIS inside the Ubuntu-22.04 WSL distro for the SCS pipeline.
# Invoked from PowerShell via `wsl -d Ubuntu-22.04 -u root bash /mnt/c/.../setup_trellis_wsl.sh`.
#
# Idempotent — safe to run multiple times.
# Skips flash-attn (needs more VRAM than our 8 GB; setup.sh's --xformers
# path is the right replacement for our hardware).

set -e
export PATH=/opt/conda/bin:$PATH
export DEBIAN_FRONTEND=noninteractive

echo "=== Stage 1: clone TRELLIS (if needed) ==="
cd /root
if [ ! -d /root/TRELLIS ]; then
    git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git
else
    cd /root/TRELLIS && git pull --recurse-submodules || true
fi
cd /root/TRELLIS
echo "TRELLIS HEAD: $(git rev-parse --short HEAD)"

echo ""
echo "=== Stage 2: create conda env 'trellis' if missing ==="
if ! conda env list | grep -q '^trellis '; then
    # Use the new-env path documented in TRELLIS README, but explicitly
    # request the inference subset (no training, no flash-attn).
    bash setup.sh --new-env --basic --xformers --spconv --mipgaussian --kaolin --nvdiffrast --diffoctreerast 2>&1 | tail -40 || {
        echo "FATAL: setup.sh failed"
        exit 1
    }
else
    echo "Conda env 'trellis' already exists, skipping create."
fi

echo ""
echo "=== Stage 3: verify install ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis
python -c "
import torch
print('torch:', torch.__version__, 'cuda available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('  device:', torch.cuda.get_device_name(0))
    print('  total VRAM:', torch.cuda.get_device_properties(0).total_memory // (1024**2), 'MiB')
" || true

# Quick imports
python -c "
import sys
sys.path.insert(0, '/root/TRELLIS')
ok = True
try:
    import trellis; print('trellis: ok')
except Exception as e: print('trellis: FAIL —', e); ok = False
try:
    from trellis.pipelines import TrellisImageTo3DPipeline; print('TrellisImageTo3DPipeline: ok')
except Exception as e: print('TrellisImageTo3DPipeline: FAIL —', e); ok = False
print('verification PASSED' if ok else 'verification FAILED')
" || true

echo ""
echo "Setup complete."
