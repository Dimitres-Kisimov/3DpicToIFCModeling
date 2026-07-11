#!/bin/bash
# queue3_verified.sh — corrected model queue with per-model preflight gates.
#
# Lessons from the 2026-07-11 night run baked in:
#  - PREFLIGHT: each model must generate ONE real mesh (>50 KB) before its batch;
#    an import error costs 1 minute, not a silent 180-item fabrication.
#  - POSTCHECK: >10 outputs with <3 distinct file sizes = fabricated -> SUSPECT.
#  - Weight caches are evicted between models (25-50 GB volume, 30 GB container).
#  - SAM 3D needs precomputed rembg masks for internet photos (manual fix #8:
#    rembg conflicts with its numpy pin, so masks come from the triposg env).
#  - All markers append to /workspace/logs/queue_rest.log (the monitored file).
L=/workspace/logs/queue_rest.log
HUB=/root/.cache/huggingface/hub
cd /workspace/cloud_bundle
mark(){ echo "$1 $(date +%H:%M)" >> $L; }

python3 - <<'PY'
import json
items = json.load(open('manifest.json'))
json.dump(items[:1], open('preflight_manifest.json', 'w'))
PY

run_model(){
  m=$1
  mark "Q3_PREFLIGHT $m"
  rm -f out_preflight/$m/*.glb 2>/dev/null
  python run_cloud_benchmark.py --models $m --manifest preflight_manifest.json --out out_preflight >> $L 2>&1
  f=$(ls out_preflight/$m/*.glb 2>/dev/null | head -1)
  if [ -z "$f" ] || [ "$(stat -c%s "$f")" -lt 50000 ]; then
    mark "Q3_PREFLIGHT_FAIL $m — batch skipped, see cloud_bundle/logs/$m.log"
    return 1
  fi
  mark "Q3_PREFLIGHT_OK $m ($(stat -c%s "$f") bytes)"
  python run_cloud_benchmark.py --models $m >> $L 2>&1
  python run_cloud_benchmark.py --models $m --manifest bench170_manifest.json --out out170 >> $L 2>&1
  sizes=$(ls -la out170/$m/*.glb 2>/dev/null | awk '{print $5}' | sort -u | wc -l)
  n=$(ls out170/$m/*.glb 2>/dev/null | wc -l)
  mark "Q3_DONE $m r10=$(ls out/$m/*.glb 2>/dev/null | wc -l) s170=$n distinct_sizes=$sizes"
  if [ "$n" -gt 10 ] && [ "$sizes" -lt 3 ]; then
    mark "Q3_SUSPECT $m — outputs nearly identical, treat as fabricated"
  fi
}

mark Q3_START
# clear stubs from crashed/quota-era runs so skip-exists cannot keep garbage
find out out170 out_seg out_preflight -name '*.glb' -size -50k -delete 2>/dev/null

run_model trellis
rm -rf $HUB/models--microsoft--TRELLIS-image-large $HUB/models--facebook--dinov2* 2>/dev/null

run_model instantmesh
rm -rf $HUB/models--TencentARC--InstantMesh $HUB/models--sudo-ai--* 2>/dev/null

run_model sf3d
python run_cloud_benchmark.py --models sf3d --out out_seg >> $L 2>&1   # raw-vs-cutout A/B, research-10
rm -rf $HUB/models--stabilityai--stable-fast-3d 2>/dev/null

mark Q3_MASKS
/workspace/envs/triposg/bin/python precompute_masks.py bench170_manifest.json masks >> $L 2>&1
/workspace/envs/triposg/bin/python precompute_masks.py manifest.json masks >> $L 2>&1

run_model sam3d
rm -rf $HUB/models--facebook--sam-3d-objects 2>/dev/null

mark Q3_TRELLIS2_PREP
for e in /opt/envs/trellis /opt/envs/sam3d /opt/envs/instantmesh; do
  $e/bin/pip freeze > /workspace/$(basename $e)-freeze.txt 2>/dev/null
done
# finished models' envs are scripted-rebuildable; TRELLIS 2.0 needs their space
rm -rf /opt/envs/trellis /opt/envs/sam3d 2>/dev/null
rm -rf /workspace/envs/trellis2 2>/dev/null            # corrupt partial from the mv incident
mkdir -p /opt/envs/trellis2 && python3 -m venv /opt/envs/trellis2
ln -sfn /opt/envs/trellis2 /workspace/envs/trellis2
bash install_models.sh trellis2 >> /workspace/logs/rebuild_trellis2.log 2>&1
mark Q3_TRELLIS2_INSTALLED
/workspace/envs/trellis2/bin/python -c 'import flash_attn' 2>/dev/null || export ATTN_BACKEND=sdpa
run_model trellis2

python score_all.py --out out >> $L 2>&1
python score_all.py --out out_seg >> $L 2>&1
python app_pipeline_test.py out/ apptest/ --repo /workspace/repo3d >> $L 2>&1
mark "QUEUE3_ALL_DONE vol=$(du -sh /workspace 2>/dev/null | cut -f1) free=$(df -h / | tail -1 | awk '{print $4}')"
