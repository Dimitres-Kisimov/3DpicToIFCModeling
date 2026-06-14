#!/bin/bash
# Fixes the PyTorch 2.4.0 + mkl >= 2024.1 symbol mismatch by pinning mkl back
# to 2024.0.0 (last version that exports iJIT_NotifyEvent), then re-runs the
# xformers / spconv / mipgaussian installs that setup.sh skipped because torch
# couldn't import.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

LOG=/root/trellis_fix.log
exec > "$LOG" 2>&1

echo "=== TRELLIS mkl fix start: $(date) ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

echo
echo "=== Stage 1: downgrade mkl ==="
# 2023.1.0 is the last pre-2025 version available on the defaults channel; it
# still exports iJIT_NotifyEvent (the symbol PyTorch 2.4.0 links against).
# Also pin mkl-service / mkl_fft / mkl_random to versions that match.
conda install -n trellis -y \
    mkl=2023.1.0 \
    mkl-service=2.4.0 \
    mkl_fft=1.3.10 \
    mkl_random=1.2.7
echo

echo "=== Stage 2: verify torch import + CUDA ==="
python <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("  device:", torch.cuda.get_device_name(0))
    print("  total VRAM:", torch.cuda.get_device_properties(0).total_memory // (1024 ** 2), "MiB")
    print("  torch.version.cuda:", torch.version.cuda)
PY
TORCH_RV=$?
echo
echo "=== Stage 2 exit code: $TORCH_RV ==="

if [ "$TORCH_RV" -ne 0 ]; then
    echo "FATAL: torch still broken after mkl downgrade. Aborting."
    exit 1
fi

echo
echo "=== Stage 3: re-run setup.sh for the skipped extras ==="
cd /root/TRELLIS
# Don't pass --new-env (env exists). Pipe yes for any prompts.
yes | bash setup.sh --xformers --spconv --mipgaussian
SETUP_RV=$?
echo
echo "=== Stage 3 exit code: $SETUP_RV ==="

echo
echo "=== Stage 4: final verify ==="
python <<'PY'
import sys
sys.path.insert(0, "/root/TRELLIS")
ok = True
try:
    import torch
    print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
except Exception as e:
    print("torch: FAIL —", e); ok = False
try:
    import xformers
    print("xformers:", xformers.__version__)
except Exception as e:
    print("xformers: FAIL —", e); ok = False
try:
    import spconv
    print("spconv: ok (", spconv.__version__, ")")
except Exception as e:
    print("spconv: FAIL —", e); ok = False
try:
    from trellis.pipelines import TrellisImageTo3DPipeline
    print("TrellisImageTo3DPipeline: OK")
except Exception as e:
    print("TrellisImageTo3DPipeline: FAIL —", e); ok = False
print("VERIFICATION", "PASSED" if ok else "FAILED")
PY

echo
echo "=== TRELLIS mkl fix end: $(date) ==="
echo "DONE"
