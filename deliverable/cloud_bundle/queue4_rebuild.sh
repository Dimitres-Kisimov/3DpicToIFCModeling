#!/bin/bash
# queue4_rebuild.sh — overnight rebuild round: the four engines whose truncated
# envs failed tonight, ONE AT A TIME with full teardown between slots (the 30GB
# container disk fits exactly one engine's env+weights comfortably).
# Waits for QUEUE3_ALL_DONE, then: instantmesh -> sf3d -> sam3d -> trellis.
# trellis runs LAST and its env is KEPT for Study E (multi-image mode).
# Weight caches are evicted per slot; envs are deleted after their run
# (freeze list saved) EXCEPT trellis.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
CB=/workspace/cloud_bundle
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q QUEUE3_ALL_DONE $L 2>/dev/null; do sleep 120; done
mark Q4_START
pip cache purge >/dev/null 2>&1; rm -rf /tmp/cc* /tmp/pip-* /tmp/tmp* 2>/dev/null
mkdir -p /workspace/tmp
cd $CB

gate_and_run(){  # $1 model
  m=$1
  mark "Q4_PREFLIGHT $m"
  rm -f out_preflight/$m/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $m --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$m/*.glb 2>/dev/null | head -1)
  if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
    mark "Q4_PREFLIGHT_FAIL $m — slot skipped (logs/$m.log)"
    return 1
  fi
  mark "Q4_PREFLIGHT_OK $m"
  python run_cloud_benchmark.py --models $m >> $L 2>&1
  python run_cloud_benchmark.py --models $m --manifest bench170_manifest.json --out out170 >> $L 2>&1
  sizes=$(ls -la out170/$m/*.glb 2>/dev/null | awk '{print $5}' | sort -u | wc -l)
  n=$(ls out170/$m/*.glb 2>/dev/null | wc -l)
  mark "Q4_DONE $m r10=$(ls out/$m/*.glb 2>/dev/null | wc -l) s170=$n distinct_sizes=$sizes"
}

teardown(){  # $1 env-path  $2 hub-glob...
  p=$1; shift
  $p/bin/pip freeze > /workspace/$(basename $p)-freeze.txt 2>/dev/null
  rm -rf "$p" 2>/dev/null
  for g in "$@"; do rm -rf $HUB/$g 2>/dev/null; done
  mark "Q4_TEARDOWN done free=$(df -h / | tail -1 | awk '{print $4}')"
}

# ---- slot 0: TRELLIS 2.0 rescue — weights (16G) already cached; cumesh/_C.so has a
# torch ABI mismatch -> rebuild the repo's compiled extensions against the env torch
mark Q4_TRELLIS2_RESCUE
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
for ext in $(find /workspace/repos/TRELLIS2 -maxdepth 3 \( -name setup.py -o -name pyproject.toml \) 2>/dev/null | xargs -r -n1 dirname | sort -u | grep -vE '/TRELLIS2$'); do
  echo "rebuilding extension: $ext" >> $L
  /opt/envs/trellis2/bin/pip install -q --no-build-isolation --force-reinstall --no-deps "$ext" >> $L 2>&1
done
gate_and_run trellis2
rm -rf $HUB/models--microsoft--TRELLIS.2-4B $HUB/models--facebook--dinov3* 2>/dev/null
mark "Q4_TRELLIS2_SLOT_DONE free=$(df -h / | tail -1 | awk '{print $4}')"

# ---- slot 1: instantmesh (env verified, script path-fixed; weights re-download)
gate_and_run instantmesh
teardown /opt/envs/instantmesh 'models--TencentARC--InstantMesh' 'models--sudo-ai--*'

# ---- slot 2: sf3d (build vendored CUDA extensions with room to breathe)
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0
cd /workspace/repos/stable-fast-3d
/workspace/envs/sf3d/bin/pip install -q --no-build-isolation ./uv_unwrapper >> $L 2>&1
/workspace/envs/sf3d/bin/pip install -q --no-build-isolation ./texture_baker >> $L 2>&1
cd $CB
gate_and_run sf3d && python run_cloud_benchmark.py --models sf3d --out out_seg >> $L 2>&1
rm -rf $HUB/models--stabilityai--stable-fast-3d 2>/dev/null
mark "Q4_SF3D_SLOT_DONE"

# ---- slot 3: sam3d (env was recycled — full rebuild from the proven manual recipe)
mark Q4_SAM3D_REBUILD
python3 -m venv /opt/envs/sam3d
ln -sfn /opt/envs/sam3d /workspace/envs/sam3d
P=/opt/envs/sam3d/bin/pip
$P install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> $L 2>&1
$P install -q -r /workspace/repos/SAM3D/requirements.inference.txt >> $L 2>&1
$P install -q loguru timm==0.9.16 spconv-cu121==2.3.8 open3d trimesh optree==0.14.1 astor rootutils \
  randomname opencv-python==4.9.0.80 roma==1.5.1 einops xatlas==0.0.9 Rtree==1.3.0 omegaconf \
  "scikit-image==0.23.1" "tifffile==2024.8.30" "plyfile==1.0.3" "lightning==2.3.3" pyvista \
  "pymeshfix==0.17.0" igraph hydra-core seaborn "werkzeug==3.0.6" >> $L 2>&1
$P install -q "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b" >> $L 2>&1
$P install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1
$P install -q "numpy==1.26.4" >> $L 2>&1
F=/workspace/repos/SAM3D/sam3d_objects/model/backbone/tdfy_dit/modules/sparse/__init__.py
grep -q 'ATTN = "sdpa"' "$F" || sed -i '/__from_env()/a ATTN = "sdpa"' "$F"
gate_and_run sam3d
teardown /opt/envs/sam3d 'models--facebook--sam-3d-objects'

# ---- slot 4: trellis v1 (env was recycled — rebuild on the kaolin-capable stack)
mark Q4_TRELLIS_REBUILD
mkdir -p /opt/envs/trellis && python3 -m venv /opt/envs/trellis
ln -sfn /opt/envs/trellis /workspace/envs/trellis
P=/opt/envs/trellis/bin/pip
$P install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> $L 2>&1
$P install -q pillow imageio imageio-ffmpeg tqdm easydict opencv-python-headless scipy rembg \
  onnxruntime trimesh xatlas pyvista pymeshfix igraph transformers open3d plyfile safetensors >> $L 2>&1
$P install -q spconv-cu121==2.3.8 >> $L 2>&1
$P install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1
$P install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" >> $L 2>&1
echo /workspace/repos/TRELLIS > /opt/envs/trellis/lib/python3.12/site-packages/zz_trellis_repo.pth
gate_and_run trellis
rm -rf $HUB/models--microsoft--TRELLIS-image-large 2>/dev/null
# trellis env KEPT alive for Study E (multi-image run_multi_image)

python score_all.py out >> $L 2>&1
python score_all.py out_seg >> $L 2>&1
pip install -q trimesh pymeshfix fast_simplification scipy ifcopenshell >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "QUEUE4_ALL_DONE free=$(df -h / | tail -1 | awk '{print $4}') vol=$(du -sh /workspace 2>/dev/null | cut -f1)"
