#!/bin/bash
# night_shift2.sh — corrected straggler sweep after trellis1_final:
#  IM:    nvdiffrast needs the git CUDA build, not PyPI (chase special-case restored)
#  SF3D:  generic chase (env keeps losing pure-python deps; transformers et al.)
#  SAM3D: kaolin MUST come from the torch-matched find-links index (PyPI wheel is
#         ABI-mismatched: undefined c10_cuda_check_implementation)
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q CAMPAIGN_FULLY_COMPLETE $L 2>/dev/null; do sleep 180; done
while pgrep -f 'run[_]cloud_benchmark|infer[_]' > /dev/null; do sleep 180; done
mark NS2_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp
pip cache purge >/dev/null 2>&1

chase(){  # $1 pip  $2 python  $3 name  $4 test-cmd...
  p=$1; py=$2; n=$3; shift 3
  for i in 1 2 3 4 5 6 7 8; do
    ERR=$("$@" 2>&1 | tail -1)
    echo "$ERR" | grep -q OK$ && { mark "NS2_${n}_IMPORT_OK"; return 0; }
    MOD=$(echo "$ERR" | grep -oP "No module named '\K[^']+" | cut -d. -f1)
    if [ -z "$MOD" ]; then mark "NS2_${n}_STUCK $ERR"; return 1; fi
    mark "NS2_${n}_MISSING $MOD"
    case $MOD in
      nvdiffrast) $p install -q ninja; $p install -q --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast" >> $L 2>&1 ;;
      cv2) $p install -q opencv-python-headless ;;
      kaolin) $p download kaolin==0.18.0 --no-deps -d /workspace/tmp/kwheel --no-index -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1 && $p install -q --no-deps /workspace/tmp/kwheel/kaolin*.whl >> $L 2>&1 ;;
      *) $p install -q "$MOD" || { mark "NS2_${n}_PIPFAIL $MOD"; return 1; } ;;
    esac
  done
  mark "NS2_${n}_MAXITER"; return 1
}

gate_run(){  # $1 model  $2 also-r10 (yes/no)
  m=$1
  rm -f out_preflight/$m/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $m --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$m/*.glb 2>/dev/null | head -1)
  if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then mark "NS2_${m}_GATE_FAIL"; return 1; fi
  mark "NS2_${m}_GATE_OK"
  [ "$2" = yes ] && python run_cloud_benchmark.py --models $m >> $L 2>&1
  python run_cloud_benchmark.py --models $m --manifest bench170_manifest.json --out out170 >> $L 2>&1
  mark "NS2_${m}_DONE r10=$(ls out/$m/*.glb 2>/dev/null | wc -l) s187=$(ls out170/$m/*.glb 2>/dev/null | wc -l)"
}

# IM (env exists; sweep owed)
chase /opt/envs/instantmesh/bin/pip /opt/envs/instantmesh/bin/python IM \
  /opt/envs/instantmesh/bin/python -c "import sys; sys.path.insert(0,'/workspace/repos/InstantMesh'); from src.utils.mesh_util import save_obj; print('OK')" \
  && gate_run instantmesh no
rm -rf $HUB/models--TencentARC--InstantMesh $HUB/models--sudo-ai--* 2>/dev/null

# SF3D (access granted; env needs the chase)
chase /workspace/envs/sf3d/bin/pip /workspace/envs/sf3d/bin/python SF3D \
  /workspace/envs/sf3d/bin/python -c "import sys; sys.path.insert(0,'/workspace/repos/stable-fast-3d'); from sf3d.system import SF3D; print('OK')" \
  && { gate_run sf3d yes; python run_cloud_benchmark.py --models sf3d --out out_seg >> $L 2>&1; }
rm -rf $HUB/models--stabilityai--stable-fast-3d 2>/dev/null

# SAM3D (kaolin from the right index; numpy 2.1 already set)
chase /opt/envs/sam3d/bin/pip /opt/envs/sam3d/bin/python SAM3D \
  /opt/envs/sam3d/bin/python /tmp/t_sam3d.py \
  && gate_run sam3d yes
rm -rf $HUB/models--facebook--sam-3d-objects 2>/dev/null

python score_all.py out >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "NS2_ALL_DONE — stragglers swept; campaign at maximum achievable coverage"
