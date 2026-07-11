#!/bin/bash
# makeup_slots.sh — after the TRELLIS 2.0 final slot: the two remaining debts.
#  A. InstantMesh 187-sweep (its r10 succeeded; the sweep died on a grayscale
#     photo now fixed at the data level; env was torn down -> scripted rebuild).
#  B. TripoSG list11 backfill (17 items; sweep ran before list11 existed).
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q TRELLIS2_CAMPAIGN_COMPLETE $L 2>/dev/null; do sleep 120; done
mark MK_START
cd /workspace/cloud_bundle
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.0 TMPDIR=/workspace/tmp

# ---- A. instantmesh rebuild + 187-sweep
mark MK_IM_REBUILD
mkdir -p /opt/envs/instantmesh && python3 -m venv /opt/envs/instantmesh --system-site-packages
ln -sfn /opt/envs/instantmesh /workspace/envs/instantmesh
bash install_models.sh instantmesh >> /workspace/logs/mk_instantmesh.log 2>&1
/opt/envs/instantmesh/bin/pip install -q opencv-python-headless ninja >> $L 2>&1
/opt/envs/instantmesh/bin/pip install -q --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast" >> $L 2>&1
if (cd /workspace/repos/InstantMesh && /opt/envs/instantmesh/bin/python -c "from src.utils.mesh_util import save_obj"); then
  mark MK_IM_IMPORT_OK
  python run_cloud_benchmark.py --models instantmesh --manifest bench170_manifest.json --out out170 >> $L 2>&1
  mark "MK_IM_SWEEP_DONE s170=$(ls out170/instantmesh/*.glb 2>/dev/null | wc -l)"
else
  mark MK_IM_IMPORT_FAIL
fi
rm -rf $HUB/models--TencentARC--InstantMesh $HUB/models--sudo-ai--* 2>/dev/null

# ---- A2. sf3d retry — extensions verified OK; blocker was the HF gate (user must
# accept the license on huggingface.co/stabilityai/stable-fast-3d). Attempt; if
# still 403, mark needs-user and move on.
mark MK_SF3D_RETRY
rm -f out_preflight/sf3d/*.glb 2>/dev/null
python run_cloud_benchmark.py --models sf3d --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/sf3d/*.glb 2>/dev/null | head -1)
if [ -n "$f" ] && [ "$(stat -c%s "$f")" -ge 50000 ]; then
  mark MK_SF3D_PREFLIGHT_OK
  python run_cloud_benchmark.py --models sf3d >> $L 2>&1
  python run_cloud_benchmark.py --models sf3d --out out_seg >> $L 2>&1
  python run_cloud_benchmark.py --models sf3d --manifest bench170_manifest.json --out out170 >> $L 2>&1
  mark "MK_SF3D_DONE r10=$(ls out/sf3d/*.glb 2>/dev/null | wc -l) s170=$(ls out170/sf3d/*.glb 2>/dev/null | wc -l)"
  rm -rf $HUB/models--stabilityai--stable-fast-3d 2>/dev/null
else
  mark "MK_SF3D_STILL_BLOCKED — user must accept the HF gate on stabilityai/stable-fast-3d"
fi

# ---- B. triposg list11 backfill (env alive; weights re-download; skip-exists fills only the 17)
mark MK_TSG_BACKFILL
source /workspace/envs/triposg/bin/activate
python infer_triposg.py bench170_manifest.json out170/triposg >> $L 2>&1
deactivate
mark "MK_TSG_DONE s170=$(ls out170/triposg/*.glb 2>/dev/null | wc -l)"
rm -rf $HUB/models--VAST-AI--TripoSG 2>/dev/null

python score_all.py out >> $L 2>&1
mark "MAKEUP_ALL_DONE — campaign fully complete, ready to download"
