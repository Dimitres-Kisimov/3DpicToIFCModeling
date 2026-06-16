#!/bin/bash
# Smoke-test run_instantmesh_wsl.py end-to-end inside the trellis conda env.
# First run downloads Zero123++ + InstantMesh weights (~3 GB) from HF.
# Logs to /root/instantmesh_smoke.log.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOG=/root/instantmesh_smoke.log
exec > "$LOG" 2>&1

echo "=== InstantMesh smoke test start: $(date) ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

IMG=/mnt/c/Users/dinos/Downloads/3DpicToIFCModeling/backend/triposr/examples/chair.png
OUT=/tmp/instantmesh_chair.glb

if [ ! -f "$IMG" ]; then
    echo "FATAL: input image not found at $IMG"
    exit 1
fi

echo "Input:  $IMG"
echo "Output: $OUT"
echo

# Save the Zero123++ intermediate 6-view sheet so we can see what the
# multi-view generator produced from the input photo.
export SCS_INSTANTMESH_DEBUG_SHEET=/mnt/c/Users/dinos/Downloads/instantmesh_zero123_sheet.png

python /mnt/c/Users/dinos/Downloads/3DpicToIFCModeling/backend/python-scripts/run_instantmesh_wsl.py "$IMG" "$OUT"
RV=$?

echo
echo "=== adapter exit code: $RV ==="
echo
if [ -f "$OUT" ]; then
    echo "GLB size: $(stat -c %s "$OUT") bytes"
    # Persist immediately to Windows-side so we don't lose it to /tmp cleanup
    cp "$OUT" /mnt/c/Users/dinos/Downloads/instantmesh_chair.glb
    echo "copied to /mnt/c/Users/dinos/Downloads/instantmesh_chair.glb"
else
    echo "WARN: no GLB output produced"
fi
echo
echo "=== InstantMesh smoke test end: $(date) ==="
echo "DONE"
