#!/bin/bash
# Install nvdiffrast — requires CUDA toolkit (nvcc + cudart-dev headers) which
# the conda pytorch package doesn't ship. We pull a minimal nvcc + cudart-dev
# subset from the nvidia channel (avoids the 3 GB full toolkit).

export PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

LOG=/root/nvdiffrast_install.log
exec > "$LOG" 2>&1

echo "=== nvdiffrast install start: $(date) ==="
source /opt/conda/etc/profile.d/conda.sh
conda activate trellis

echo
echo "=== Stage 1: install CUDA 11.8 nvcc + cudart-dev ==="
conda install -y -n trellis -c nvidia/label/cuda-11.8.0 \
    cuda-nvcc cuda-cudart-dev cuda-libraries-dev 2>&1 | tail -10
echo

echo "=== Stage 2: probe CUDA_HOME ==="
# After install nvcc is at $CONDA_PREFIX/bin/nvcc and headers at
# $CONDA_PREFIX/include. Set CUDA_HOME to $CONDA_PREFIX.
export CUDA_HOME=$CONDA_PREFIX
echo CUDA_HOME=$CUDA_HOME
which nvcc
nvcc --version 2>&1 | tail -3 || echo "nvcc not found yet"
echo

echo "=== Stage 3: install nvdiffrast (compiles CUDA ext) ==="
pip install --no-build-isolation --no-input \
    "git+https://github.com/NVlabs/nvdiffrast/" 2>&1 | tail -20
echo

echo "=== Stage 4: verify ==="
python -c "import nvdiffrast.torch as dr; print('nvdiffrast import: OK', dr.__file__)" 2>&1

echo
echo "=== nvdiffrast install end: $(date) ==="
echo "DONE"
