#!/bin/bash
# Smoke-test run_trellis_wsl.py end-to-end inside the trellis conda env.
# First run downloads ~3 GB of weights from HuggingFace (one-time).
# Logs to /root/trellis_smoke.log.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOG=/root/trellis_smoke.log
exec > "$LOG" 2>&1

echo "=== TRELLIS smoke test start: $(date) ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

IMG=/mnt/c/Users/dinos/Downloads/3DpicToIFCModeling/backend/triposr/examples/chair.png
OUT=/tmp/trellis_chair.glb

if [ ! -f "$IMG" ]; then
    echo "FATAL: input image not found at $IMG"
    exit 1
fi

echo "Input:  $IMG"
echo "Output: $OUT"
echo

# Use the run_trellis_wsl.py adapter exactly as the Windows-side bridge will.
python /mnt/c/Users/dinos/Downloads/3DpicToIFCModeling/backend/python-scripts/run_trellis_wsl.py "$IMG" "$OUT"
RV=$?

echo
echo "=== adapter exit code: $RV ==="
echo
if [ -f "$OUT" ]; then
    echo "GLB size: $(stat -c %s "$OUT") bytes"
else
    echo "WARN: no GLB output produced"
fi
echo
echo "=== TRELLIS smoke test end: $(date) ==="
echo "DONE"
