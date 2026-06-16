#!/bin/bash
# Recover from the failed bulk install: install everything in requirements.txt
# EXCEPT nvdiffrast first (so the rest gets in), then install nvdiffrast on its
# own with --no-build-isolation.
#
# Also relaxes the transformers/diffusers version pins — those pins (4.34.1 /
# 0.20.2) are from InstantMesh's original era (early 2024) and are too old for
# PyTorch 2.4.0. We'll let pip resolve the latest compatible.

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

LOG=/root/instantmesh_fix.log
exec > "$LOG" 2>&1

echo "=== InstantMesh fix start: $(date) ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

echo
echo "=== Stage 1: install Python deps (excluding nvdiffrast) ==="
# transformers/diffusers are already loosened — pin only what InstantMesh
# can't run without. Bypass version pins that conflict with our torch 2.4.
pip install --no-input \
    pytorch-lightning \
    huggingface-hub \
    einops \
    omegaconf \
    torchmetrics \
    webdataset \
    accelerate \
    tensorboard \
    PyMCubes \
    'transformers>=4.40' \
    'diffusers>=0.27' \
    bitsandbytes \
    'imageio[ffmpeg]' \
    plyfile \
    2>&1 | tail -10

echo
echo "=== Stage 2: install nvdiffrast with --no-build-isolation ==="
pip install --no-build-isolation --no-input \
    "git+https://github.com/NVlabs/nvdiffrast/" \
    2>&1 | tail -15

echo
echo "=== Stage 3: verify ==="
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

import torch
print(f"  cuda available: {torch.cuda.is_available()}")
_try("diffusers", lambda: __import__("diffusers"))
_try("transformers", lambda: __import__("transformers"))
_try("pytorch_lightning", lambda: __import__("pytorch_lightning"))
_try("einops", lambda: __import__("einops"))
_try("omegaconf", lambda: __import__("omegaconf"))
_try("nvdiffrast", lambda: __import__("nvdiffrast"))
_try("PyMCubes", lambda: __import__("mcubes"))

# Try the InstantMesh repo-internal imports
_try("InstantMesh src.utils.train_util",
     lambda: __import__("src.utils.train_util", fromlist=["instantiate_from_config"]))

print()
print("VERIFICATION", "PASSED" if ok else "FAILED")
PY

echo
echo "=== InstantMesh fix end: $(date) ==="
echo "DONE"
