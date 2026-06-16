#!/bin/bash
# Install InstantMesh (TencentARC, Apache-2.0) inside the existing `trellis`
# conda env in WSL Ubuntu-22.04. Reuses pytorch+xformers+spconv+kaolin from
# yesterday's TRELLIS install — shorter, no env churn.
#
# Logs to /root/instantmesh_install.log.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

LOG=/root/instantmesh_install.log
exec > "$LOG" 2>&1

echo "=== InstantMesh install start: $(date) ==="

source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

echo
echo "=== Stage 1: clone InstantMesh ==="
cd /root
if [ ! -d /root/InstantMesh ]; then
    git clone https://github.com/TencentARC/InstantMesh.git
else
    cd /root/InstantMesh && git pull || true
fi
cd /root/InstantMesh
echo "InstantMesh HEAD: $(git rev-parse --short HEAD)"

echo
echo "=== Stage 2: install Python deps ==="
# InstantMesh's own requirements.txt — install everything missing into the
# existing trellis env. Pin nothing; let pip resolve against torch 2.4.0.
# -y for any prompts.
pip install --no-input -r requirements.txt 2>&1 | tail -30

echo
echo "=== Stage 3: verify InstantMesh imports ==="
python <<'PY'
import sys
sys.path.insert(0, "/root/InstantMesh")

ok = True
def _try(name, fn):
    global ok
    try:
        fn()
        print(f"  {name}: OK")
    except Exception as e:
        print(f"  {name}: FAIL — {e}")
        ok = False

_try("torch", lambda: __import__("torch"))

import torch
print(f"  cuda available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  device: {torch.cuda.get_device_name(0)}")

_try("diffusers", lambda: __import__("diffusers"))
_try("transformers", lambda: __import__("transformers"))
_try("pytorch_lightning", lambda: __import__("pytorch_lightning"))
_try("einops", lambda: __import__("einops"))
_try("omegaconf", lambda: __import__("omegaconf"))
_try("rembg", lambda: __import__("rembg"))
_try("imageio", lambda: __import__("imageio"))
_try("nerfacc", lambda: __import__("nerfacc"))
_try("xatlas", lambda: __import__("xatlas"))
_try("trimesh", lambda: __import__("trimesh"))

print()
print("VERIFICATION", "PASSED" if ok else "FAILED")
PY

echo
echo "=== InstantMesh install end: $(date) ==="
echo "DONE"
