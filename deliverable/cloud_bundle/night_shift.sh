#!/bin/bash
# night_shift.sh — autonomous overnight completion: IM sweep, SF3D (gate now
# granted), SAM 3D (numpy-2.1 + kaolin-0.18 fix), each sequential with weight
# eviction between slots; ends by emitting SAM3D_CAMPAIGN_COMPLETE so the armed
# trellis1_final.sh chains automatically.
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }
mark NS_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

gate(){  # $1 model -> 0 if preflight mesh ok
  rm -f out_preflight/$1/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $1 --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$1/*.glb 2>/dev/null | head -1)
  [ -n "$f" ] && [ "$(stat -c%s "$f")" -ge 50000 ]
}

# ---- slot 1: InstantMesh 187-sweep (env missing xatlas; chase up to 6 rounds)
for i in 1 2 3 4 5 6; do
  ERR=$(cd /workspace/repos/InstantMesh && /opt/envs/instantmesh/bin/python -c "from src.utils.mesh_util import save_obj; print('OK')" 2>&1 | tail -1)
  [ "$ERR" = "OK" ] && break
  MOD=$(echo "$ERR" | grep -oP "No module named '\K[^']+" | cut -d. -f1)
  [ -z "$MOD" ] && break
  mark "NS_IM_MISSING $MOD"
  /opt/envs/instantmesh/bin/pip install -q "$MOD" >> $L 2>&1
done
if [ "$ERR" = "OK" ]; then
  mark NS_IM_IMPORT_OK
  if gate instantmesh; then
    mark NS_IM_GATE_OK
    python run_cloud_benchmark.py --models instantmesh --manifest bench170_manifest.json --out out170 >> $L 2>&1
    mark "NS_IM_DONE s187=$(ls out170/instantmesh/*.glb 2>/dev/null | wc -l)"
  else
    mark NS_IM_GATE_FAIL
  fi
else
  mark "NS_IM_ABORT $ERR"
fi
rm -rf $HUB/models--TencentARC--InstantMesh $HUB/models--sudo-ai--* 2>/dev/null

# ---- slot 2: SF3D (access granted by user tonight; extensions verified)
if gate sf3d; then
  mark NS_SF3D_GATE_OK
  python run_cloud_benchmark.py --models sf3d >> $L 2>&1
  python run_cloud_benchmark.py --models sf3d --out out_seg >> $L 2>&1
  python run_cloud_benchmark.py --models sf3d --manifest bench170_manifest.json --out out170 >> $L 2>&1
  mark "NS_SF3D_DONE r10=$(ls out/sf3d/*.glb 2>/dev/null | wc -l) s187=$(ls out170/sf3d/*.glb 2>/dev/null | wc -l)"
else
  mark NS_SF3D_GATE_FAIL
fi
rm -rf $HUB/models--stabilityai--stable-fast-3d 2>/dev/null

# ---- slot 3: SAM 3D — the numpy-2.1 + kaolin-0.18 resolution
P=/opt/envs/sam3d/bin/pip
$P install -q "numpy==2.1.*" >> $L 2>&1
$P install -q kaolin==0.18.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html >> $L 2>&1
R=$(/opt/envs/sam3d/bin/python /tmp/t_sam3d.py 2>&1 | tail -1)
mark "NS_SAM3D_IMPORT $R"
if echo "$R" | grep -q IMPORT_OK; then
  if gate sam3d; then
    mark "NS_SAM3D_GATE_OK — first verified SAM 3D mesh"
    python run_cloud_benchmark.py --models sam3d >> $L 2>&1
    python run_cloud_benchmark.py --models sam3d --manifest bench170_manifest.json --out out170 >> $L 2>&1
    mark "NS_SAM3D_DONE r10=$(ls out/sam3d/*.glb 2>/dev/null | wc -l) s187=$(ls out170/sam3d/*.glb 2>/dev/null | wc -l)"
  else
    mark NS_SAM3D_GATE_FAIL
  fi
else
  mark NS_SAM3D_IMPORT_STILL_BROKEN
fi
rm -rf $HUB/models--facebook--sam-3d-objects 2>/dev/null

python score_all.py out >> $L 2>&1
pip install -q trimesh pymeshfix fast_simplification scipy ifcopenshell >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "SAM3D_CAMPAIGN_COMPLETE — night shift done; trellis1_final chains next"
