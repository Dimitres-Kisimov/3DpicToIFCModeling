#!/bin/bash
# trellis2_final.sh — TRELLIS 2.0's dedicated retry slot after queue4.
# Preconditions handled elsewhere: CuMesh rebuilt from source (user-approved,
# Q4_CUMESH_REBUILT marker), weights re-download below (evicted earlier).
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

until grep -q QUEUE4_ALL_DONE $L 2>/dev/null; do sleep 120; done
mark T2F_START
cd /workspace/cloud_bundle

# full pipeline import gate first — cheap, and names the next blocker if any
if ! /opt/envs/trellis2/bin/python -c "
import sys; sys.path.insert(0, '/workspace/repos/TRELLIS2')
import os; os.environ.setdefault('ATTN_BACKEND', 'sdpa')
from trellis2.pipelines import Trellis2ImageTo3DPipeline
print('T2_IMPORT_OK')" >> $L 2>&1; then
  mark "T2F_IMPORT_FAIL — see last traceback in this log; slot aborted"
  exit 1
fi
mark T2F_IMPORT_OK

mark "T2F_PREFLIGHT (weights re-download ~16G)"
rm -f out_preflight/trellis2/*.glb 2>/dev/null
python run_cloud_benchmark.py --models trellis2 --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
f=$(ls out_preflight/trellis2/*.glb 2>/dev/null | head -1)
if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
  mark "T2F_PREFLIGHT_FAIL — see logs/trellis2.log"
  exit 1
fi
mark "T2F_PREFLIGHT_OK ($(stat -c%s "$f") bytes) — FIRST TRELLIS 2.0 MESH"

python run_cloud_benchmark.py --models trellis2 >> $L 2>&1
python run_cloud_benchmark.py --models trellis2 --manifest bench170_manifest.json --out out170 >> $L 2>&1
sizes=$(ls -la out170/trellis2/*.glb 2>/dev/null | awk '{print $5}' | sort -u | wc -l)
mark "T2F_DONE r10=$(ls out/trellis2/*.glb 2>/dev/null | wc -l) s170=$(ls out170/trellis2/*.glb 2>/dev/null | wc -l) distinct_sizes=$sizes"
rm -rf $HUB/models--microsoft--TRELLIS.2-4B $HUB/models--facebook--dinov3* 2>/dev/null

python score_all.py out >> $L 2>&1
pip install -q trimesh pymeshfix fast_simplification scipy ifcopenshell >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "TRELLIS2_CAMPAIGN_COMPLETE free=$(df -h / | tail -1 | awk '{print $4}')"
